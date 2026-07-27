"""Pure expected-cost math — no I/O."""

from conjure_finder.engine import (
    GUARANTEE_POOL_MAX,
    _expected_action_clicks,
    _expected_sessions,
    _hit_probability,
)


def test_pool_leq_guarantee_max_is_one_session() -> None:
    for pool in (1, 2, GUARANTEE_POOL_MAX):
        assert _expected_sessions(pool) == 1.0
        assert _hit_probability(pool) == 1.0


def test_pool_three_expected_sessions() -> None:
    # Uniform position among 3, peeks 2 → E[sessions] = 4/3.
    assert abs(_expected_sessions(3) - 4.0 / 3.0) < 1e-9


def test_empty_pool() -> None:
    assert _expected_sessions(0) == float("inf")
    assert _hit_probability(0) == 0.0


def test_author_same_pool_small_is_guarantee() -> None:
    clicks, guar = _expected_action_clicks(2)
    assert guar is True
    assert clicks == 0.0


def test_reshape_filtered_pool_not_false_guarantee() -> None:
    """solo+rating pool≤2 must not claim conjure-alone when character has hundreds."""
    clicks, guar = _expected_action_clicks(2, conjure_pool=437)
    assert guar is False
    assert clicks > 1.0
    # Almost always miss on conjure; E[clicks | miss] = (2+1)/2 = 1.5
    assert abs(clicks - 1.5) < 0.05


def test_author_large_pool_peeks_shrink_remainder() -> None:
    clicks, guar = _expected_action_clicks(10, hits=1)
    assert guar is False
    # p_miss * (8+1)/2
    p_miss = 1.0 - _hit_probability(10, 1)
    assert abs(clicks - p_miss * 4.5) < 1e-9
