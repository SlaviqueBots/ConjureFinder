"""Expected FE/hour for Netherrealm / Deep Space resonance farming."""

from __future__ import annotations

from dataclasses import dataclass

# Fixed drop rate from a boss kill.
NR_DROP_CHANCE = 0.025
NR_DROP_AMOUNT = 90

# Perk package (taken all-or-nothing):
# Each NR that would drop is independently resolved as:
#   3%  → Deep Space  (then 66% chance to duplicate that DS)
#   90% → destroyed
#   7%  → stays Netherrealm
# Equivalent to: convert-to-DS first (3%), then of the remainder 90% erase.
PERK_TO_DS = 0.03
PERK_ERASE = 0.90
PERK_DS_DUPLICATE = 0.66


@dataclass(frozen=True)
class Inputs:
    nr_price_fe: float
    ds_price_fe: float
    bosses_per_map: float
    map_duration_min: float


@dataclass(frozen=True)
class HourlyResult:
    fe_per_hour_without: float
    fe_per_hour_with: float
    delta_fe_per_hour: float  # with − without (positive = perk package is a gain)

    bosses_per_hour: float
    expected_nr_per_boss_without: float
    expected_nr_per_boss_with: float
    expected_ds_per_boss_with: float


def _expected_ds_from_one_nr() -> float:
    """Expected Deep Space count produced from one original NR under perks."""
    # 3% convert; then 66% of those are duplicated → multiplier 1.66
    return PERK_TO_DS * (1.0 + PERK_DS_DUPLICATE)


def _expected_nr_kept_from_one_nr() -> float:
    """Expected NR kept from one original NR under perks (after convert + erase)."""
    survive_rate = 1.0 - PERK_TO_DS  # not converted to DS
    keep_rate = survive_rate * (1.0 - PERK_ERASE)
    return keep_rate


def expected_per_boss(nr_price: float, ds_price: float) -> tuple[float, float, float, float]:
    """Return (fe_without, fe_with, expected_nr_with, expected_ds_with) per boss."""
    base_nr = NR_DROP_CHANCE * NR_DROP_AMOUNT
    fe_without = base_nr * nr_price

    nr_kept = base_nr * _expected_nr_kept_from_one_nr()
    ds_got = base_nr * _expected_ds_from_one_nr()
    fe_with = nr_kept * nr_price + ds_got * ds_price
    return fe_without, fe_with, nr_kept, ds_got


def calculate(inp: Inputs) -> HourlyResult:
    if inp.map_duration_min <= 0:
        raise ValueError("Map duration must be > 0")
    if inp.bosses_per_map < 0:
        raise ValueError("Bosses per map must be ≥ 0")
    if inp.nr_price_fe < 0 or inp.ds_price_fe < 0:
        raise ValueError("Prices must be ≥ 0")

    maps_per_hour = 60.0 / inp.map_duration_min
    bosses_per_hour = inp.bosses_per_map * maps_per_hour

    fe_boss_wo, fe_boss_w, nr_w, ds_w = expected_per_boss(
        inp.nr_price_fe, inp.ds_price_fe
    )
    fe_wo = bosses_per_hour * fe_boss_wo
    fe_w = bosses_per_hour * fe_boss_w
    base_nr = NR_DROP_CHANCE * NR_DROP_AMOUNT

    return HourlyResult(
        fe_per_hour_without=fe_wo,
        fe_per_hour_with=fe_w,
        delta_fe_per_hour=fe_w - fe_wo,
        bosses_per_hour=bosses_per_hour,
        expected_nr_per_boss_without=base_nr,
        expected_nr_per_boss_with=nr_w,
        expected_ds_per_boss_with=ds_w,
    )
