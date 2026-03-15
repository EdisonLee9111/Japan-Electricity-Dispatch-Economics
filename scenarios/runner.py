"""Scenario runner — execute dispatch under modified assumptions.

The runner takes a ScenarioConfig, applies its modifications to the base-case
inputs (fleet capacities, fuel prices, demand), and runs the Level 1 dispatch
solver.  Results are stored in a unified format for comparison.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Sequence

import pandas as pd

from .config import ScenarioConfig, ALL_SCENARIOS, BASE_CASE

# Re-use the Level 1 dispatch pipeline
from engine.dispatch_solver import (
    load_processed_inputs,
    run_level1_dispatch,
    write_level1_results,
)


def _resolve_project_root(project_root: str | Path | None = None) -> Path:
    if project_root is None:
        return Path(__file__).resolve().parents[1]
    return Path(project_root).resolve()


# ── Input modification ───────────────────────────────────────────────────────

def apply_scenario(
    inputs: dict[str, pd.DataFrame],
    scenario: ScenarioConfig,
) -> dict[str, pd.DataFrame]:
    """Return a *copy* of inputs with scenario modifications applied.

    Modifications:
    - Fleet capacity overrides (nuclear, solar, wind)
    - Fuel-price multipliers (LNG, coal, oil — applied to time-series)
    - Demand multiplier
    """
    modified = {k: v.copy() for k, v in inputs.items()}

    # ── Fleet capacity overrides ─────────────────────────────────────────
    fleet = modified["fleet"]

    capacity_overrides: dict[str, float | None] = {
        "nuclear": scenario.nuclear_capacity_gw,
        "solar": scenario.solar_capacity_gw,
        "wind": scenario.wind_capacity_gw,
    }

    for fuel_type, gw in capacity_overrides.items():
        if gw is not None:
            mask = fleet["fuel_type"] == fuel_type
            if mask.any():
                fleet.loc[mask, "installed_capacity_mw"] = gw * 1000.0

    modified["fleet"] = fleet

    # ── Fuel-price multipliers ───────────────────────────────────────────
    fuel_prices = modified["fuel_prices"]

    if scenario.lng_price_multiplier != 1.0:
        fuel_prices["lng_japan_jpy_mmbtu"] = (
            fuel_prices["lng_japan_jpy_mmbtu"] * scenario.lng_price_multiplier
        )

    if scenario.coal_price_multiplier != 1.0:
        fuel_prices["coal_aus_jpy_mt"] = (
            fuel_prices["coal_aus_jpy_mt"] * scenario.coal_price_multiplier
        )

    if scenario.oil_price_multiplier != 1.0:
        fuel_prices["crude_wti_jpy_bbl"] = (
            fuel_prices["crude_wti_jpy_bbl"] * scenario.oil_price_multiplier
        )

    modified["fuel_prices"] = fuel_prices

    # ── Demand multiplier ────────────────────────────────────────────────
    if scenario.demand_multiplier != 1.0:
        demand = modified["demand"]
        demand["demand"] = demand["demand"] * scenario.demand_multiplier
        modified["demand"] = demand

    return modified


# ── Single scenario execution ────────────────────────────────────────────────

def run_scenario(
    base_inputs: dict[str, pd.DataFrame],
    scenario: ScenarioConfig,
    *,
    verbose: bool = True,
) -> dict:
    """Run Level 1 dispatch for one scenario and return structured results.

    Returns
    -------
    dict with keys:
        scenario   — ScenarioConfig
        dispatch   — DataFrame (per-fleet per-timestamp)
        prices     — DataFrame (per-timestamp summary)
        elapsed_s  — float
    """
    if verbose:
        print(f"  → {scenario.name}: {scenario.description[:80]}…")

    t0 = time.time()
    modified_inputs = apply_scenario(base_inputs, scenario)
    dispatch_df, price_df = run_level1_dispatch(modified_inputs)
    elapsed = time.time() - t0

    if verbose:
        mean_price = price_df["clearing_price_jpy_kwh"].mean()
        print(f"    {len(price_df):,} timestamps, "
              f"mean price {mean_price:.2f} JPY/kWh, "
              f"{elapsed:.1f}s")

    return {
        "scenario": scenario,
        "dispatch": dispatch_df,
        "prices": price_df,
        "elapsed_s": elapsed,
    }


# ── Batch execution ──────────────────────────────────────────────────────────

def run_all_scenarios(
    base_inputs: dict[str, pd.DataFrame],
    scenarios: Sequence[ScenarioConfig] | None = None,
    *,
    verbose: bool = True,
) -> dict[str, dict]:
    """Run all scenarios and return results keyed by scenario name.

    Parameters
    ----------
    base_inputs : dict
        Loaded processed inputs (from load_processed_inputs).
    scenarios : sequence of ScenarioConfig, optional
        Defaults to ALL_SCENARIOS (base + 3 counterfactuals).
    verbose : bool
        Print progress.

    Returns
    -------
    dict[str, dict]
        {scenario_name: {scenario, dispatch, prices, elapsed_s}}
    """
    if scenarios is None:
        scenarios = ALL_SCENARIOS

    if verbose:
        print(f"Running {len(scenarios)} scenario(s) …")

    results: dict[str, dict] = {}
    for sc in scenarios:
        results[sc.name] = run_scenario(base_inputs, sc, verbose=verbose)

    if verbose:
        total = sum(r["elapsed_s"] for r in results.values())
        print(f"All scenarios complete ({total:.1f}s total)")

    return results


# ── Persistence ──────────────────────────────────────────────────────────────

def write_scenario_results(
    results: dict[str, dict],
    project_root: str | Path | None = None,
) -> list[Path]:
    """Write each scenario's dispatch and price CSVs to output/results/."""
    root = _resolve_project_root(project_root)
    output_dir = root / "output" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for name, res in results.items():
        dispatch_path = output_dir / f"scenario_{name}_dispatch.csv"
        prices_path = output_dir / f"scenario_{name}_prices.csv"

        res["dispatch"].to_csv(dispatch_path, index=False)
        res["prices"].to_csv(prices_path, index=False)

        written.extend([dispatch_path, prices_path])

    return written
