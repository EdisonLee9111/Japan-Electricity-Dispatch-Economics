"""Scenario comparator — compute deltas and summary statistics.

Compares each counterfactual scenario against the base case across
key dispatch-economics metrics defined in the dev plan.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import numpy as np


# ── Per-scenario summary ─────────────────────────────────────────────────────

def _generation_mix_twh(dispatch_df: pd.DataFrame) -> pd.Series:
    """Total generation by fuel type in TWh."""
    gen = dispatch_df.groupby("fuel_type")["dispatched_mwh"].sum() / 1e6
    return gen.rename("generation_twh")


def _capacity_factor(dispatch_df: pd.DataFrame) -> pd.Series:
    """Average capacity factor by fuel type (dispatched / installed)."""
    grouped = dispatch_df.groupby("fuel_type").agg(
        dispatched_mwh=("dispatched_mwh", "sum"),
        installed_capacity_mw=("installed_capacity_mw", "first"),
        interval_hours=("interval_hours", "first") if "interval_hours" in dispatch_df.columns else ("dispatched_mwh", "count"),
    )
    n_timestamps = dispatch_df["timestamp"].nunique()
    if "interval_hours" in dispatch_df.columns:
        interval_h = dispatch_df["interval_hours"].iloc[0]
    else:
        interval_h = 0.5  # default 30-min
    total_hours = n_timestamps * interval_h
    grouped["capacity_factor"] = (
        grouped["dispatched_mwh"]
        / (grouped["installed_capacity_mw"] * total_hours)
    ).clip(0, 1)
    return grouped["capacity_factor"]


def _startup_count(dispatch_df: pd.DataFrame) -> pd.Series:
    """Count startup events by fuel type (only meaningful for UC results)."""
    if "startup" not in dispatch_df.columns:
        return pd.Series(dtype=float, name="startup_count")
    startups = dispatch_df[dispatch_df["startup"] > 0].groupby("fuel_type")["startup"].sum()
    return startups.rename("startup_count")


def _marginal_fuel_hours(prices_df: pd.DataFrame) -> pd.Series:
    """Number of timestamps each fuel type is the marginal price-setter."""
    if "marginal_fuel" not in prices_df.columns:
        return pd.Series(dtype=float, name="marginal_hours")
    counts = prices_df["marginal_fuel"].value_counts()
    return counts.rename("marginal_hours")


def _low_price_hours(prices_df: pd.DataFrame, threshold_jpy_kwh: float = 5.0) -> int:
    """Count timestamps where clearing price < threshold (proxy for duck curve severity)."""
    col = "clearing_price_jpy_kwh"
    if col not in prices_df.columns:
        return 0
    return int((prices_df[col] < threshold_jpy_kwh).sum())


def _curtailment_twh(prices_df: pd.DataFrame) -> float:
    """Total renewable curtailment in TWh."""
    col = "renewable_curtailment_mwh"
    if col not in prices_df.columns:
        return 0.0
    return float(prices_df[col].sum() / 1e6)


def summarise_scenario(
    dispatch_df: pd.DataFrame,
    prices_df: pd.DataFrame,
    name: str = "",
) -> dict:
    """Compute summary metrics for a single scenario run."""
    avg_price_kwh = float(prices_df["clearing_price_jpy_kwh"].mean())
    std_price_kwh = float(prices_df["clearing_price_jpy_kwh"].std())
    max_price_kwh = float(prices_df["clearing_price_jpy_kwh"].max())
    min_price_kwh = float(prices_df["clearing_price_jpy_kwh"].min())

    gen_mix = _generation_mix_twh(dispatch_df)
    cap_factors = _capacity_factor(dispatch_df)
    marginal_hours = _marginal_fuel_hours(prices_df)
    low_hours = _low_price_hours(prices_df)
    curtailment = _curtailment_twh(prices_df)
    total_gen_twh = float(gen_mix.sum())

    return {
        "name": name,
        "avg_price_jpy_kwh": avg_price_kwh,
        "std_price_jpy_kwh": std_price_kwh,
        "max_price_jpy_kwh": max_price_kwh,
        "min_price_jpy_kwh": min_price_kwh,
        "total_generation_twh": total_gen_twh,
        "generation_mix_twh": gen_mix.to_dict(),
        "capacity_factors": cap_factors.to_dict(),
        "marginal_hours": marginal_hours.to_dict(),
        "low_price_hours_below_5yen": low_hours,
        "curtailment_twh": curtailment,
    }


# ── Pairwise comparison ─────────────────────────────────────────────────────

def compare_scenario(
    base_summary: dict,
    scenario_summary: dict,
) -> dict:
    """Compute deltas between scenario and base case."""
    delta: dict = {
        "scenario": scenario_summary["name"],
        "vs_base": base_summary["name"],
    }

    # Price changes
    delta["avg_price_change_jpy_kwh"] = (
        scenario_summary["avg_price_jpy_kwh"] - base_summary["avg_price_jpy_kwh"]
    )
    delta["avg_price_change_pct"] = (
        delta["avg_price_change_jpy_kwh"] / base_summary["avg_price_jpy_kwh"] * 100
        if base_summary["avg_price_jpy_kwh"] != 0 else 0.0
    )

    # Generation mix delta (TWh)
    base_gen = base_summary["generation_mix_twh"]
    sc_gen = scenario_summary["generation_mix_twh"]
    all_fuels = sorted(set(base_gen.keys()) | set(sc_gen.keys()))
    delta["generation_delta_twh"] = {
        f: sc_gen.get(f, 0.0) - base_gen.get(f, 0.0) for f in all_fuels
    }

    # Capacity factor delta
    base_cf = base_summary["capacity_factors"]
    sc_cf = scenario_summary["capacity_factors"]
    delta["capacity_factor_delta"] = {
        f: sc_cf.get(f, 0.0) - base_cf.get(f, 0.0)
        for f in sorted(set(base_cf.keys()) | set(sc_cf.keys()))
    }

    # Low-price hours delta
    delta["low_price_hours_delta"] = (
        scenario_summary["low_price_hours_below_5yen"]
        - base_summary["low_price_hours_below_5yen"]
    )

    # Curtailment delta
    delta["curtailment_delta_twh"] = (
        scenario_summary["curtailment_twh"] - base_summary["curtailment_twh"]
    )

    # Marginal hours shift
    base_mh = base_summary["marginal_hours"]
    sc_mh = scenario_summary["marginal_hours"]
    all_marginals = sorted(set(base_mh.keys()) | set(sc_mh.keys()))
    delta["marginal_hours_delta"] = {
        f: sc_mh.get(f, 0) - base_mh.get(f, 0) for f in all_marginals
    }

    return delta


# ── Batch comparison ─────────────────────────────────────────────────────────

def compare_all(
    results: dict[str, dict],
    base_name: str = "base",
) -> tuple[pd.DataFrame, list[dict]]:
    """Compare all scenarios against the base case.

    Parameters
    ----------
    results : dict
        Output from runner.run_all_scenarios().
    base_name : str
        Name of the base-case scenario.

    Returns
    -------
    summary_table : DataFrame
        One row per scenario with headline metrics.
    deltas : list[dict]
        Detailed pairwise comparison dicts for each non-base scenario.
    """
    if base_name not in results:
        raise KeyError(f"Base scenario '{base_name}' not found in results.")

    # Build summaries
    summaries: dict[str, dict] = {}
    for name, res in results.items():
        summaries[name] = summarise_scenario(
            res["dispatch"], res["prices"], name=name
        )

    # Summary table (flat)
    rows = []
    for name, s in summaries.items():
        row = {
            "scenario": name,
            "avg_price_jpy_kwh": s["avg_price_jpy_kwh"],
            "std_price_jpy_kwh": s["std_price_jpy_kwh"],
            "total_generation_twh": s["total_generation_twh"],
            "low_price_hours": s["low_price_hours_below_5yen"],
            "curtailment_twh": s["curtailment_twh"],
        }
        # Add per-fuel generation columns
        for fuel, twh in sorted(s["generation_mix_twh"].items()):
            row[f"gen_{fuel}_twh"] = twh
        # Add per-fuel capacity factor columns
        for fuel, cf in sorted(s["capacity_factors"].items()):
            row[f"cf_{fuel}"] = cf
        rows.append(row)

    summary_table = pd.DataFrame(rows).set_index("scenario")

    # Pairwise deltas
    base_summary = summaries[base_name]
    deltas = []
    for name, s in summaries.items():
        if name == base_name:
            continue
        deltas.append(compare_scenario(base_summary, s))

    return summary_table, deltas


def print_comparison_report(
    summary_table: pd.DataFrame,
    deltas: list[dict],
) -> None:
    """Print a human-readable comparison report to stdout."""
    print("\n" + "=" * 72)
    print("SCENARIO COMPARISON REPORT")
    print("=" * 72)

    # Headline metrics
    print("\n── Headline Metrics ──")
    cols = ["avg_price_jpy_kwh", "total_generation_twh", "low_price_hours", "curtailment_twh"]
    display_cols = [c for c in cols if c in summary_table.columns]
    print(summary_table[display_cols].to_string(float_format="{:.3f}".format))

    # Per-scenario deltas
    for d in deltas:
        print(f"\n── {d['scenario']} vs {d['vs_base']} ──")
        print(f"  Avg price change: {d['avg_price_change_jpy_kwh']:+.3f} JPY/kWh "
              f"({d['avg_price_change_pct']:+.1f}%)")
        print(f"  Low-price hours Δ: {d['low_price_hours_delta']:+d}")
        print(f"  Curtailment Δ: {d['curtailment_delta_twh']:+.3f} TWh")

        print("  Generation Δ (TWh):")
        for fuel, twh in sorted(d["generation_delta_twh"].items(), key=lambda x: -abs(x[1])):
            if abs(twh) > 0.001:
                print(f"    {fuel:15s} {twh:+.3f}")

        print("  Capacity factor Δ:")
        for fuel, cf in sorted(d["capacity_factor_delta"].items(), key=lambda x: -abs(x[1])):
            if abs(cf) > 0.001:
                print(f"    {fuel:15s} {cf:+.4f}")

    print("\n" + "=" * 72)


# ── Persistence ──────────────────────────────────────────────────────────────

def write_comparison(
    summary_table: pd.DataFrame,
    deltas: list[dict],
    project_root: str | Path | None = None,
) -> list[Path]:
    """Write comparison outputs to output/results/."""
    if project_root is None:
        root = Path(__file__).resolve().parents[1]
    else:
        root = Path(project_root).resolve()

    output_dir = root / "output" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []

    # Summary table
    summary_path = output_dir / "scenario_summary.csv"
    summary_table.to_csv(summary_path)
    written.append(summary_path)

    # Delta details as separate CSVs
    for d in deltas:
        name = d["scenario"]

        gen_delta = pd.Series(d["generation_delta_twh"], name="delta_twh")
        cf_delta = pd.Series(d["capacity_factor_delta"], name="delta_cf")
        combined = pd.DataFrame({"generation_delta_twh": gen_delta, "capacity_factor_delta": cf_delta})

        delta_path = output_dir / f"scenario_delta_{name}_vs_base.csv"
        combined.to_csv(delta_path, index_label="fuel_type")
        written.append(delta_path)

    return written
