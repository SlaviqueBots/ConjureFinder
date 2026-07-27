"""Candidate ordering / anchor coverage — no network."""

from __future__ import annotations

from conjure_finder.engine import (
    FORCE_PAIR_ANCHORS,
    PricedTag,
    _collect_pairs,
    _iter_candidates,
)


def _g(name: str, count: int) -> PricedTag:
    return PricedTag(name=name, category=0, price=25, kind="general", post_count=count)


def _p(name: str, count: int, *, cat: int = 4) -> PricedTag:
    return PricedTag(name=name, category=cat, price=50, kind="premium", post_count=count)


def test_iter_candidates_main_cost_order() -> None:
    priced = [
        _g(f"g{i:02d}", 100 + i)
        for i in range(12)
    ] + [
        _g("late_big", 50_000),
        _p("char_a", 20_000, cat=4),
        _p("artist_a", 5_000, cat=1),
    ]
    main, deferred = _iter_candidates(priced)
    costs = [c for c, _, _ in main]
    assert costs == sorted(costs), f"cost order broken: {costs}"
    assert any(t[0].name == "late_big" for _c, _e, t in deferred)
    assert not any(t[0].name == "late_big" for _c, _e, t in main)


def test_large_singles_are_deferred_not_main() -> None:
    priced = [
        _g("common_a", 10_000),
        _g("common_b", 20_000),
        _g("late_solo", 99_999),
        _p("char_x", 8_000, cat=4),
    ]
    main, deferred = _iter_candidates(priced)
    assert any(t[0].name == "late_solo" for _c, _e, t in deferred)
    assert not any(
        len(t) == 1 and t[0].name == "late_solo" for _c, _e, t in main
    )


def test_force_anchors_cover_rarest_generals() -> None:
    generals = [_g(f"g{i:02d}", i + 1) for i in range(20)]
    pairs = _collect_pairs(
        generals,
        generals,
        max_pairs=40,
        force_anchors=FORCE_PAIR_ANCHORS,
        same_side=True,
    )
    rarest = {t.name for t in generals[:FORCE_PAIR_ANCHORS]}
    seen = set()
    for _est, tags in pairs:
        for t in tags:
            seen.add(t.name)
    assert rarest <= seen
    assert FORCE_PAIR_ANCHORS >= 5
