"""Bulk wishlist — metadata clustering + ownership math (no I/O)."""

from conjure_finder.bulk import (
    _covered_for_tags,
    _metadata_beckon_candidates,
    _metadata_conjure_candidates,
)
from conjure_finder.engine import (
    PostMeta,
    PricedTag,
    TargetSnap,
    _expected_action_clicks,
)
from conjure_finder.urls import flatten_wishlist_urls
from bot.core.config import AUTHOR_COST, CONJURE_PRICE_PREMIUM, RESHAPE_COST


def _tag(name: str, *, price: int = 25, category: int = 0, count: int = 100) -> PricedTag:
    return PricedTag(
        name=name,
        category=category,
        price=price,
        kind="general" if category == 0 else "premium",
        post_count=count,
    )


def _snap(post_id: int, tags: list[PricedTag], *, artist: str | None = None, char: str | None = None) -> TargetSnap:
    meta = PostMeta(
        rating="e",
        has_solo=True,
        artists=[_tag(artist, price=50, category=1, count=200)] if artist else [],
        characters=[_tag(char, price=50, category=4, count=500)] if char else [],
    )
    return TargetSnap(
        post_id=post_id,
        priced=list(tags),
        tag_set={t.name for t in tags},
        file_ext="jpg",
        meta=meta,
        hell_mode="",
        preview_url=f"https://example.com/{post_id}.jpg",
        page_url=f"https://danbooru.donmai.us/posts/{post_id}",
    )


def test_flatten_wishlist_urls_dedupes_and_flattens() -> None:
    raw = """
https://danbooru.donmai.us/posts/1
https://danbooru.donmai.us/posts/2 | https://danbooru.donmai.us/posts/3
# comment
https://danbooru.donmai.us/posts/2
"""
    urls = flatten_wishlist_urls(raw)
    assert len(urls) == 3
    assert urls[0].endswith("/1")
    assert urls[1].endswith("/2")
    assert urls[2].endswith("/3")


def test_shared_rare_tag_preferred_over_unique_common() -> None:
    shared = _tag("rare_pose", count=8)
    common = _tag("1girl", count=2_000_000)
    a = _snap(1, [shared, common])
    b = _snap(2, [shared, _tag("solo", count=500_000)])
    c = _snap(3, [common, _tag("looking_at_viewer", count=800_000)])
    targets = [a, b, c]
    priced = [shared, common, _tag("solo", count=500_000), _tag("looking_at_viewer", count=800_000)]
    cands = _metadata_conjure_candidates(targets, priced)
    assert cands
    top_tags = [t.name for t in cands[0][2]]
    assert "rare_pose" in top_tags
    assert cands[0][1] >= 2


def test_beckon_skips_ocean_tags_even_when_shared() -> None:
    """Regression: pool capped at 100 made /beckon ass look cheap."""
    ocean = _tag("ass", count=2_000_000)
    solo = _tag("solo", count=1_500_000)
    rare = _tag("curled_horns", count=18)
    targets = [
        _snap(1, [ocean, solo, rare]),
        _snap(2, [ocean, solo, rare]),
        _snap(3, [ocean, solo, rare]),
    ]
    priced = [ocean, solo, rare]
    beckon = _metadata_beckon_candidates(targets, priced)
    names = [r[2].name for r in beckon]
    assert "ass" not in names
    assert "solo" not in names
    assert "curled_horns" in names

    conjure = _metadata_conjure_candidates(targets, priced)
    conjure_names = {t.name for _e, _h, tags in conjure for t in tags}
    assert "ass" not in conjure_names
    assert "solo" not in conjure_names
    assert "curled_horns" in conjure_names


def test_live_pool_ceiling_rejected() -> None:
    from conjure_finder.bulk import _live_pool_usable

    assert _live_pool_usable(40) is True
    assert _live_pool_usable(99) is True
    assert _live_pool_usable(100) is False
    assert _live_pool_usable(0) is False


def test_covered_for_tags_intersection() -> None:
    t1 = _snap(1, [_tag("a"), _tag("b")])
    t2 = _snap(2, [_tag("a"), _tag("c")])
    t3 = _snap(3, [_tag("b"), _tag("c")])
    covered = _covered_for_tags([t1, t2, t3], ["a", "b"])
    assert [c.post_id for c in covered] == [1]


def test_owned_author_skips_conjure_premium() -> None:
    """Already-have author: only Author clicks, not 50 + clicks."""
    pool, hits = 40, 3
    e_clicks_owned = (pool + 1) / float(hits + 1)
    owned_cur = AUTHOR_COST * e_clicks_owned
    e_clicks, _guar = _expected_action_clicks(pool, hits=hits)
    unowned_cur = CONJURE_PRICE_PREMIUM + AUTHOR_COST * e_clicks
    assert owned_cur < unowned_cur
    assert abs(unowned_cur - owned_cur - CONJURE_PRICE_PREMIUM) < 1e-6 or owned_cur < unowned_cur - 30


def test_owned_character_skips_conjure_premium() -> None:
    pool, hits, conjure_pool = 20, 2, 400
    e_clicks_owned = (pool + 1) / float(hits + 1)
    owned_cur = RESHAPE_COST * e_clicks_owned
    e_clicks, _ = _expected_action_clicks(pool, hits=hits, conjure_pool=conjure_pool)
    unowned_cur = CONJURE_PRICE_PREMIUM + RESHAPE_COST * e_clicks
    assert owned_cur + 30 < unowned_cur


def test_save_roundtrip(tmp_path, monkeypatch) -> None:
    from conjure_finder import saves
    from conjure_finder.bulk import BulkCoveredPost, BulkPath, BulkResult
    from conjure_finder.engine import ConjureOption

    monkeypatch.setattr(saves, "SAVES_DIR", tmp_path)
    result = BulkResult(
        source="danbooru",
        paths=[
            BulkPath(
                option=ConjureOption(
                    tags=("rare_pose",),
                    cost=25,
                    pool_size=8,
                    guaranteed=False,
                    command="/conjure rare_pose",
                    hell_mode="",
                    expected_sessions=2.0,
                    expected_currency=50.0,
                    path="conjure",
                ),
                covered=(
                    BulkCoveredPost(
                        post_id=1,
                        preview_url="https://example.com/1.jpg",
                        page_url="https://danbooru.donmai.us/posts/1",
                    ),
                ),
            )
        ],
        urls=["https://danbooru.donmai.us/posts/1"],
        own_author=False,
        own_character=True,
        checked=3,
        wishlist_size=1,
    )
    path = saves.save_bulk_result(result, "test save")
    loaded = saves.load_bulk_result(path)
    assert loaded.own_character is True
    assert loaded.wishlist_size == 1
    assert len(loaded.paths) == 1
    assert loaded.paths[0].option.command == "/conjure rare_pose"
    assert loaded.paths[0].covered[0].post_id == 1
