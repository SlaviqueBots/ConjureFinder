"""Unit tests for TL resonance expected-value math."""

from __future__ import annotations

import math

import pytest

from tl_resonance.calc import (
    NR_DROP_AMOUNT,
    NR_DROP_CHANCE,
    Inputs,
    _expected_ds_from_one_nr,
    _expected_nr_kept_from_one_nr,
    calculate,
    expected_per_boss,
)


def test_perk_rates_per_nr() -> None:
    # 3% → DS × 1.66 duplicate expectation
    assert _expected_ds_from_one_nr() == pytest.approx(0.03 * 1.66)
    # Remaining 97%, then 10% survive erase → 9.7% stay NR
    assert _expected_nr_kept_from_one_nr() == pytest.approx(0.97 * 0.10)


def test_default_prices_per_boss() -> None:
    nr_p, ds_p = 0.12, 3.0
    fe_wo, fe_w, nr_w, ds_w = expected_per_boss(nr_p, ds_p)
    base = NR_DROP_CHANCE * NR_DROP_AMOUNT  # 2.25
    assert fe_wo == pytest.approx(base * nr_p)
    assert nr_w == pytest.approx(base * 0.097)
    assert ds_w == pytest.approx(base * 0.03 * 1.66)
    assert fe_w == pytest.approx(nr_w * nr_p + ds_w * ds_p)


def test_hourly_scales_with_pace() -> None:
    # 2 bosses / map, 3 min maps → 20 maps/h → 40 bosses/h
    r = calculate(
        Inputs(nr_price_fe=0.12, ds_price_fe=3.0, bosses_per_map=2, map_duration_min=3)
    )
    assert r.bosses_per_hour == pytest.approx(40.0)
    fe_wo, fe_w, _, _ = expected_per_boss(0.12, 3.0)
    assert r.fe_per_hour_without == pytest.approx(40.0 * fe_wo)
    assert r.fe_per_hour_with == pytest.approx(40.0 * fe_w)
    assert r.delta_fe_per_hour == pytest.approx(r.fe_per_hour_with - r.fe_per_hour_without)


def test_rejects_bad_duration() -> None:
    with pytest.raises(ValueError):
        calculate(
            Inputs(nr_price_fe=0.12, ds_price_fe=3.0, bosses_per_map=1, map_duration_min=0)
        )


def test_zero_bosses_zero_income() -> None:
    r = calculate(
        Inputs(nr_price_fe=0.12, ds_price_fe=3.0, bosses_per_map=0, map_duration_min=5)
    )
    assert r.fe_per_hour_without == 0.0
    assert r.fe_per_hour_with == 0.0
    assert math.isclose(r.delta_fe_per_hour, 0.0)
