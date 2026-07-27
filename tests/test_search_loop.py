"""Search-loop regressions with a fake counter (no network)."""

from __future__ import annotations

from typing import Any

import pytest

from conjure_finder.engine import (
    PricedTag,
    PostMeta,
    TargetSnap,
    _search_targets,
)


class FakeCountSession:
    """In-memory pool map: frozenset(tag names) → live pool size."""

    def __init__(
        self,
        source: str,
        hell_mode: str,
        pools: dict[frozenset[str], int],
        query_pools: dict[str, int] | None = None,
    ) -> None:
        self.source = source
        self.hell_mode = hell_mode
        self.pools = pools
        self.query_pools = query_pools or {}
        self.probed: list[frozenset[str]] = []

    async def start(self) -> None:
        return None

    async def aclose(self) -> None:
        return None

    async def __call__(self, tags: list[str]) -> int:
        key = frozenset(tags)
        self.probed.append(key)
        if key in self.pools:
            return self.pools[key]
        # Default: large non-guarantee pool.
        return 50

    async def count_query(self, query: str) -> int:
        if query in self.query_pools:
            return self.query_pools[query]
        # Roster paths — keep expensive so conjure wins in these tests.
        return 500


def _tag(
    name: str,
    *,
    price: int,
    count: int,
    category: int = 0,
) -> PricedTag:
    kind = "premium" if price >= 50 else "general"
    return PricedTag(
        name=name,
        category=category,
        price=price,
        kind=kind,
        post_count=count,
    )


def _target(
    priced: list[PricedTag],
    *,
    post_id: int = 1,
    rating: str = "g",
    has_solo: bool = False,
) -> TargetSnap:
    artists = [t for t in priced if t.category == 1]
    characters = [t for t in priced if t.category == 4]
    return TargetSnap(
        post_id=post_id,
        priced=priced,
        tag_set={t.name for t in priced},
        file_ext="jpg",
        meta=PostMeta(
            rating=rating,
            has_solo=has_solo,
            artists=artists,
            characters=characters,
        ),
        hell_mode="",
        warnings=[],
    )


def _patch_counter(
    monkeypatch: pytest.MonkeyPatch,
    pools: dict[frozenset[str], int],
    query_pools: dict[str, int] | None = None,
) -> list[FakeCountSession]:
    created: list[FakeCountSession] = []

    def factory(source: str, hell_mode: str) -> FakeCountSession:
        fake = FakeCountSession(source, hell_mode, pools, query_pools)
        created.append(fake)
        return fake

    monkeypatch.setattr("conjure_finder.engine._CountSession", factory)
    return created


@pytest.mark.asyncio
async def test_r1zen_race_prefers_cost_75_guarantee(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pool-3 distractor must not displace lying_on_lap+r1zen (pool 2) at cost 75."""
    priced = [
        _tag("lying_on_lap", price=25, count=4_000),
        _tag("black_robe", price=25, count=3_000),
        _tag("yokozuwari", price=25, count=2_500),
        _tag("r1zen", price=50, count=120, category=1),
        _tag("fern_(sousou_no_frieren)", price=50, count=20_000, category=4),
    ]
    pools = {
        frozenset({"lying_on_lap", "r1zen"}): 2,
        frozenset({"black_robe", "r1zen"}): 3,  # near-miss at same cost tier
        frozenset({"yokozuwari", "r1zen"}): 8,
        frozenset({"fern_(sousou_no_frieren)", "r1zen"}): 2,  # cost 100 trap
        frozenset({"lying_on_lap", "fern_(sousou_no_frieren)"}): 40,
        frozenset({"black_robe", "lying_on_lap"}): 20,
    }
    _patch_counter(monkeypatch, pools)
    result = await _search_targets("danbooru", [_target(priced)], "")
    assert result.best is not None
    assert result.best.guaranteed is True
    assert result.best.cost == 75
    assert set(result.best.tags) == {"lying_on_lap", "r1zen"}
    assert result.best.pool_size == 2


@pytest.mark.asyncio
async def test_early_late_cost_25_beats_cost_50_guarantee(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deferred large-count single still runs in cost-25 tier before cost-50."""
    priced = [
        _tag("late_solo", price=25, count=99_999),  # late bucket by metadata
        _tag("pair_a", price=25, count=40),
        _tag("pair_b", price=25, count=50),
    ]
    pools = {
        frozenset({"late_solo"}): 2,
        frozenset({"pair_a", "pair_b"}): 2,
        frozenset({"pair_a"}): 40,
        frozenset({"pair_b"}): 50,
    }
    _patch_counter(monkeypatch, pools)
    result = await _search_targets("danbooru", [_target(priced)], "")
    assert result.best is not None
    assert result.best.guaranteed is True
    assert result.best.cost == 25
    assert result.best.tags == ("late_solo",)


@pytest.mark.asyncio
async def test_dominance_skip_does_not_drop_cheap_live_guarantee(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Huge metadata est must not skip a cost-25 single when floor is higher."""
    priced = [
        _tag("inflated_solo", price=25, count=10_000_000),
        _tag("noise_a", price=25, count=80),
        _tag("noise_b", price=25, count=90),
    ]
    pools = {
        frozenset({"inflated_solo"}): 2,
        frozenset({"noise_a", "noise_b"}): 8,  # sets a non-guarantee floor first
        frozenset({"noise_a"}): 80,
        frozenset({"noise_b"}): 90,
    }
    created = _patch_counter(monkeypatch, pools)
    result = await _search_targets("danbooru", [_target(priced)], "")
    assert result.best is not None
    assert result.best.guaranteed is True
    assert result.best.cost == 25
    assert result.best.tags == ("inflated_solo",)
    probed = {k for fake in created for k in fake.probed}
    assert frozenset({"inflated_solo"}) in probed


@pytest.mark.asyncio
async def test_danbooru_solo_fast_path_verifies_live_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Metadata pool≤2 with live pool 50 must not return a false solo guarantee."""
    priced = [
        _tag("stale_rare", price=25, count=1),  # metadata says guarantee
        _tag("pair_a", price=25, count=30),
        _tag("pair_b", price=25, count=40),
    ]
    pools = {
        frozenset({"stale_rare"}): 50,  # live: not a guarantee
        frozenset({"pair_a", "pair_b"}): 2,
        frozenset({"pair_a"}): 30,
        frozenset({"pair_b"}): 40,
    }
    _patch_counter(monkeypatch, pools)
    result = await _search_targets("danbooru", [_target(priced)], "")
    assert result.best is not None
    assert result.best.guaranteed is True
    assert set(result.best.tags) == {"pair_a", "pair_b"}
    assert result.best.cost == 50
    # Must not have accepted the stale solo.
    assert result.best.tags != ("stale_rare",)


@pytest.mark.asyncio
async def test_reshape_small_filter_does_not_block_conjure_guarantee(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filtered reshape pool≤2 with huge character tag must not beat a cost-50 conjure."""
    priced = [
        _tag("mismatched_irises", price=25, count=5_000),
        _tag("female_masturbation", price=25, count=8_000),
        _tag("sanhua_(wuthering_waves)", price=50, count=437, category=4),
        _tag("noise_g", price=25, count=20_000),
    ]
    pools = {
        frozenset({"mismatched_irises", "female_masturbation"}): 2,
        frozenset({"mismatched_irises", "noise_g"}): 40,
        frozenset({"female_masturbation", "noise_g"}): 50,
        frozenset({"sanhua_(wuthering_waves)", "mismatched_irises"}): 30,
        frozenset({"sanhua_(wuthering_waves)", "female_masturbation"}): 20,
    }
    query_pools = {
        "sanhua_(wuthering_waves)": 437,
        "solo sanhua_(wuthering_waves) rating:q": 2,
    }
    _patch_counter(monkeypatch, pools, query_pools)
    result = await _search_targets(
        "danbooru",
        [_target(priced, rating="q", has_solo=True)],
        "",
    )
    assert result.best is not None
    assert result.best.path == "conjure"
    assert result.best.guaranteed is True
    assert result.best.cost == 50
    assert set(result.best.tags) == {"mismatched_irises", "female_masturbation"}


@pytest.mark.asyncio
async def test_equal_expected_currency_still_probes_guarantee_tier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cost-50 pool-4 (~75 cur) must not skip a cost-75 pool-1 guarantee."""
    priced = [
        _tag("skin_fang", price=25, count=4_000),
        _tag("bent_over", price=25, count=50_000),
        _tag("noise_g", price=25, count=3_000),
        _tag("solipsist", price=50, count=200, category=1),
    ]
    pools = {
        frozenset({"skin_fang", "noise_g"}): 4,  # cost 50 → ~75 cur floor
        frozenset({"bent_over", "solipsist"}): 1,  # cost 75 guarantee
        frozenset({"skin_fang", "solipsist"}): 4,
        frozenset({"noise_g", "solipsist"}): 20,
        frozenset({"bent_over", "skin_fang"}): 80,
        frozenset({"bent_over", "noise_g"}): 90,
    }
    created = _patch_counter(monkeypatch, pools)
    result = await _search_targets("danbooru", [_target(priced)], "")
    assert result.best is not None
    assert result.best.guaranteed is True
    assert result.best.cost == 75
    assert set(result.best.tags) == {"bent_over", "solipsist"}
    probed = {k for fake in created for k in fake.probed}
    assert frozenset({"bent_over", "solipsist"}) in probed
