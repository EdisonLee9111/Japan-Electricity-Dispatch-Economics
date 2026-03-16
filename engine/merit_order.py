"""Merit-order utilities for the Level 1 dispatch engine.

This module converts processed fuel-price inputs into marginal generation costs
in JPY/MWh and builds a timestamp-specific merit order.

Key Level 1 assumptions
-----------------------
- LNG benchmark in processed data is already in JPY/MMBtu.
- Coal benchmark is JPY/metric ton and is converted to JPY/MMBtu using an
  assumed heat content of 23.8 MMBtu/mt. This is broadly consistent with
  seaborne thermal coal around ~6,000 kcal/kg.
- Oil benchmark is JPY/barrel and is converted to JPY/MMBtu using an assumed
  energy content of 5.8 MMBtu/bbl, a standard crude-oil conversion.
- Fuels without time-varying processed prices use fixed Level 1 placeholders:
    * nuclear: 80 JPY/MMBtu
    * biomass: 700 JPY/MMBtu
    * hydro / solar / wind: 0 JPY/MMBtu
  These assumptions are intentionally simple and documented here so they can
  be calibrated later without changing the solver structure.
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd

try:
    from config import get_dispatch_config
    _dispatch_cfg = get_dispatch_config()
except ImportError:
    _dispatch_cfg = {
        "renewable_fuels": {"solar", "wind"},
        "must_run_fuels": {"nuclear"},
    }

COAL_HEAT_CONTENT_MMBTU_PER_MT = 23.8
OIL_ENERGY_CONTENT_MMBTU_PER_BBL = 5.8

FIXED_FUEL_PRICE_JPY_MMBTU = {
    "nuclear": 80.0,
    "biomass": 700.0,
    "hydro": 0.0,
    "solar": 0.0,
    "wind": 0.0,
}

RENEWABLE_FUELS: set[str] = _dispatch_cfg["renewable_fuels"]
MUST_RUN_FUELS: set[str] = _dispatch_cfg["must_run_fuels"]


def coal_price_jpy_mmbtu(
    coal_price_jpy_mt: float,
    heat_content_mmbtu_per_mt: float = COAL_HEAT_CONTENT_MMBTU_PER_MT,
) -> float:
    """Convert coal price from JPY/metric ton to JPY/MMBtu."""
    if pd.isna(coal_price_jpy_mt):
        raise ValueError("Coal price is missing; expected column 'coal_aus_jpy_mt'.")
    return float(coal_price_jpy_mt) / float(heat_content_mmbtu_per_mt)


def oil_price_jpy_mmbtu(
    oil_price_jpy_bbl: float,
    energy_content_mmbtu_per_bbl: float = OIL_ENERGY_CONTENT_MMBTU_PER_BBL,
) -> float:
    """Convert oil price from JPY/barrel to JPY/MMBtu."""
    if pd.isna(oil_price_jpy_bbl):
        raise ValueError("Oil price is missing; expected column 'crude_wti_jpy_bbl'.")
    return float(oil_price_jpy_bbl) / float(energy_content_mmbtu_per_bbl)


def resolve_fuel_price_jpy_mmbtu(
    fuel_type: str,
    fuel_price_row: Mapping[str, object],
) -> tuple[float, str]:
    """Resolve a fleet's fuel price in JPY/MMBtu from the processed fuel inputs."""
    fuel_type = str(fuel_type)

    if fuel_type in {"lng_ccgt", "lng_ocgt"}:
        value = fuel_price_row.get("lng_japan_jpy_mmbtu")
        if pd.isna(value):
            raise ValueError("Missing LNG price column 'lng_japan_jpy_mmbtu'.")
        return float(value), "lng_japan_jpy_mmbtu"

    if fuel_type.startswith("coal"):
        value = fuel_price_row.get("coal_aus_jpy_mt")
        return coal_price_jpy_mmbtu(float(value)), "coal_aus_jpy_mt_to_jpy_mmbtu"

    if fuel_type == "oil":
        value = fuel_price_row.get("crude_wti_jpy_bbl")
        return oil_price_jpy_mmbtu(float(value)), "crude_wti_jpy_bbl_to_jpy_mmbtu"

    if fuel_type in FIXED_FUEL_PRICE_JPY_MMBTU:
        return FIXED_FUEL_PRICE_JPY_MMBTU[fuel_type], "fixed_assumption"

    raise ValueError(
        f"Unsupported fuel_type '{fuel_type}' for Level 1 merit-order pricing."
    )


def build_merit_order(
    fleet_df: pd.DataFrame,
    fuel_price_row: Mapping[str, object],
) -> pd.DataFrame:
    """Build a merit-order table for one timestamp.

    Parameters
    ----------
    fleet_df:
        Processed fleet table from `data/processed/fleet.csv`.
    fuel_price_row:
        Mapping-like object containing at least the fuel-price columns used by
        `resolve_fuel_price_jpy_mmbtu`.

    Returns
    -------
    pandas.DataFrame
        Fleet table with resolved fuel prices, marginal costs, dispatch groups,
        and merit-order rank.
    """
    merit = fleet_df.copy()

    required_columns = {
        "fuel_type",
        "installed_capacity_mw",
        "heat_rate_mmbtu_per_mwh",
        "variable_om_jpy_mwh",
    }
    missing = required_columns.difference(merit.columns)
    if missing:
        raise ValueError(f"fleet.csv is missing required columns: {sorted(missing)}")

    resolved = merit["fuel_type"].apply(
        lambda fuel: resolve_fuel_price_jpy_mmbtu(fuel, fuel_price_row)
    )
    merit["fuel_price_jpy_mmbtu"] = resolved.apply(lambda x: x[0])
    merit["fuel_price_source"] = resolved.apply(lambda x: x[1])

    carbon_cost = merit["carbon_cost_jpy_per_mwh"] if "carbon_cost_jpy_per_mwh" in merit.columns else 0.0
    merit["marginal_cost_jpy_mwh"] = (
        merit["fuel_price_jpy_mmbtu"] * merit["heat_rate_mmbtu_per_mwh"]
        + merit["variable_om_jpy_mwh"]
        + carbon_cost
    )

    merit["dispatch_group"] = "dispatchable"
    merit.loc[merit["fuel_type"].isin(RENEWABLE_FUELS), "dispatch_group"] = "renewable"
    merit.loc[merit["fuel_type"].isin(MUST_RUN_FUELS), "dispatch_group"] = "must_run"

    group_order = {"renewable": 0, "must_run": 1, "dispatchable": 2}
    merit["dispatch_group_order"] = merit["dispatch_group"].map(group_order)

    merit = merit.sort_values(
        by=[
            "dispatch_group_order",
            "marginal_cost_jpy_mwh",
            "fuel_type",
        ],
        ascending=[True, True, True],
    ).reset_index(drop=True)

    merit["merit_order_rank"] = range(1, len(merit) + 1)
    return merit
