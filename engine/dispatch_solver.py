from __future__ import annotations

"""Level 1 simple merit-order dispatch solver.

This module implements the MVP dispatch logic from the development plan:

- Each timestamp is solved independently.
- Solar and wind dispatch first as must-take resources using processed capacity factors.
- Nuclear is treated as must-run at a constant operational block.
- Remaining fleets are dispatched by merit order based on marginal cost.
- Oversupply is handled with renewable curtailment and price floor logic.
- Supply shortage is handled with unserved energy and price cap logic.

The solver works directly with the current processed dataset granularity
(currently 30-minute timestamps in this project), without forcing aggregation.
"""

import argparse
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    from .clearing_price import PRICE_CAP_JPY_MWH, determine_clearing_price
    from .merit_order import MUST_RUN_FUELS, RENEWABLE_FUELS, build_merit_order
except ImportError:  # pragma: no cover
    from clearing_price import PRICE_CAP_JPY_MWH, determine_clearing_price
    from merit_order import MUST_RUN_FUELS, RENEWABLE_FUELS, build_merit_order


EPSILON = 1e-9


def _resolve_project_root(project_root: str | Path | None = None) -> Path:
    """Resolve repository root path."""
    if project_root is None:
        return Path(__file__).resolve().parents[1]
    return Path(project_root).resolve()


def _require_columns(df: pd.DataFrame, required: Iterable[str], name: str) -> None:
    """Validate required columns in processed inputs."""
    missing = set(required).difference(df.columns)
    if missing:
        raise ValueError(f"{name} is missing required columns: {sorted(missing)}")


def _infer_interval_hours(timestamps: pd.Series) -> float:
    """Infer model interval from timestamps."""
    ordered = pd.to_datetime(timestamps).sort_values()
    if len(ordered) < 2:
        return 1.0

    delta = ordered.diff().dropna().median()
    if pd.isna(delta):
        return 1.0

    hours = delta.total_seconds() / 3600.0
    return float(hours if hours > 0 else 1.0)


def load_processed_inputs(
    project_root: str | Path | None = None,
) -> dict[str, pd.DataFrame]:
    """Load processed CSV inputs required for Level 1 dispatch."""
    root = _resolve_project_root(project_root)
    processed_dir = root / "data" / "processed"

    fleet = pd.read_csv(processed_dir / "fleet.csv")
    demand = pd.read_csv(
        processed_dir / "demand_profile.csv", parse_dates=["timestamp"]
    )
    renewables = pd.read_csv(
        processed_dir / "renewable_profiles.csv", parse_dates=["timestamp"]
    )
    fuel_prices = pd.read_csv(
        processed_dir / "fuel_prices.csv", parse_dates=["timestamp"]
    )

    _require_columns(
        fleet,
        [
            "fuel_type",
            "installed_capacity_mw",
            "min_stable_generation_pct",
            "heat_rate_mmbtu_per_mwh",
            "variable_om_jpy_mwh",
            "must_run",
        ],
        "fleet.csv",
    )
    _require_columns(demand, ["timestamp", "demand"], "demand_profile.csv")
    _require_columns(
        renewables,
        ["timestamp", "solar_cf", "wind_cf", "solar_available_mw", "wind_available_mw"],
        "renewable_profiles.csv",
    )
    _require_columns(
        fuel_prices,
        ["timestamp", "lng_japan_jpy_mmbtu", "coal_aus_jpy_mt", "crude_wti_jpy_bbl"],
        "fuel_prices.csv",
    )

    inputs: dict[str, pd.DataFrame] = {
        "fleet": fleet,
        "demand": demand.sort_values("timestamp").reset_index(drop=True),
        "renewables": renewables.sort_values("timestamp").reset_index(drop=True),
        "fuel_prices": fuel_prices.sort_values("timestamp").reset_index(drop=True),
    }

    jepx_path = processed_dir / "jepx_prices.csv"
    if jepx_path.exists():
        inputs["jepx_prices"] = (
            pd.read_csv(jepx_path, parse_dates=["timestamp"])
            .sort_values("timestamp")
            .reset_index(drop=True)
        )

    return inputs


def _prepare_model_table(inputs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Merge all time-series inputs into one aligned model table."""
    demand = inputs["demand"][["timestamp", "demand"]].rename(
        columns={"demand": "demand_mw"}
    )
    renewables = inputs["renewables"][
        ["timestamp", "solar_cf", "wind_cf", "solar_available_mw", "wind_available_mw"]
    ]
    fuel_prices = inputs["fuel_prices"][
        ["timestamp", "lng_japan_jpy_mmbtu", "coal_aus_jpy_mt", "crude_wti_jpy_bbl"]
    ]

    model_df = demand.merge(
        renewables, on="timestamp", how="inner", validate="one_to_one"
    )
    model_df = model_df.merge(
        fuel_prices, on="timestamp", how="inner", validate="one_to_one"
    )

    if "jepx_prices" in inputs:
        jepx = inputs["jepx_prices"][
            ["timestamp", "system_price_jpy_mwh", "tokyo_price_jpy_mwh"]
        ].rename(
            columns={
                "system_price_jpy_mwh": "actual_system_price_jpy_mwh",
                "tokyo_price_jpy_mwh": "actual_tokyo_price_jpy_mwh",
            }
        )
        model_df = model_df.merge(
            jepx, on="timestamp", how="left", validate="one_to_one"
        )

    if model_df.empty:
        raise ValueError(
            "No overlapping timestamps across demand, renewables, and fuel prices."
        )

    return model_df.sort_values("timestamp").reset_index(drop=True)


def _curtail_renewables_proportionally(
    renewable_available_mw: dict[str, float],
    excess_mw: float,
) -> tuple[dict[str, float], dict[str, float], float]:
    """Curtail solar and wind pro rata during oversupply."""
    dispatch = {fuel: float(value) for fuel, value in renewable_available_mw.items()}
    curtailed = {fuel: 0.0 for fuel in renewable_available_mw}

    total_available = sum(renewable_available_mw.values())
    if excess_mw <= EPSILON or total_available <= EPSILON:
        return dispatch, curtailed, max(float(excess_mw), 0.0)

    curtail_ratio = min(float(excess_mw) / total_available, 1.0)
    curtailed_total = 0.0

    for fuel, available in renewable_available_mw.items():
        curtail = float(available) * curtail_ratio
        dispatch[fuel] = float(available) - curtail
        curtailed[fuel] = curtail
        curtailed_total += curtail

    remaining_excess = max(float(excess_mw) - curtailed_total, 0.0)
    return dispatch, curtailed, remaining_excess


def _solve_single_timestamp(
    row: dict[str, object],
    fleet_df: pd.DataFrame,
    interval_hours: float,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Solve simple merit-order dispatch for one timestamp."""
    merit = build_merit_order(fleet_df, row)

    dispatch_by_fuel = {fuel: 0.0 for fuel in merit["fuel_type"]}
    curtailed_by_fuel = {fuel: 0.0 for fuel in merit["fuel_type"]}
    available_by_fuel: dict[str, float] = {}

    demand_mw = float(row["demand_mw"])

    for fleet_row in merit.itertuples(index=False):
        fuel = fleet_row.fuel_type
        installed_mw = float(fleet_row.installed_capacity_mw)

        if fuel == "solar":
            available_mw = installed_mw * float(row.get("solar_cf", 0.0))
        elif fuel == "wind":
            available_mw = installed_mw * float(row.get("wind_cf", 0.0))
        else:
            available_mw = installed_mw

        available_by_fuel[fuel] = max(available_mw, 0.0)

    renewable_available = {
        fuel: available_by_fuel.get(fuel, 0.0)
        for fuel in merit["fuel_type"]
        if fuel in RENEWABLE_FUELS
    }

    for fuel, available_mw in renewable_available.items():
        dispatch_by_fuel[fuel] = available_mw

    nuclear_output_mw = 0.0
    for fuel in MUST_RUN_FUELS:
        if fuel in available_by_fuel:
            nuclear_output_mw += available_by_fuel[fuel]
            dispatch_by_fuel[fuel] = available_by_fuel[fuel]

    base_supply_mw = sum(renewable_available.values()) + nuclear_output_mw
    renewable_curtailment_mw = 0.0
    noncurtailable_oversupply_mw = 0.0

    if base_supply_mw > demand_mw + EPSILON:
        excess_mw = base_supply_mw - demand_mw
        renewable_dispatch, renewable_curtailed, remaining_excess = (
            _curtail_renewables_proportionally(
                renewable_available,
                excess_mw,
            )
        )
        for fuel in renewable_dispatch:
            dispatch_by_fuel[fuel] = renewable_dispatch[fuel]
            curtailed_by_fuel[fuel] = renewable_curtailed[fuel]

        renewable_curtailment_mw = sum(renewable_curtailed.values())
        noncurtailable_oversupply_mw = remaining_excess

    residual_demand_mw = max(demand_mw - sum(dispatch_by_fuel.values()), 0.0)

    dispatchable = merit[merit["dispatch_group"] == "dispatchable"].copy()

    for fleet_row in dispatchable.itertuples(index=False):
        if residual_demand_mw <= EPSILON:
            break

        fuel = fleet_row.fuel_type
        available_mw = available_by_fuel[fuel]
        dispatch_mw = min(available_mw, residual_demand_mw)
        dispatch_by_fuel[fuel] = dispatch_mw
        residual_demand_mw -= dispatch_mw

    residual_demand_mw = max(residual_demand_mw, 0.0)

    total_generation_mw = sum(dispatch_by_fuel.values())
    unserved_energy_mw = max(demand_mw - total_generation_mw, 0.0)
    shortage = unserved_energy_mw > EPSILON
    oversupplied = base_supply_mw > demand_mw + EPSILON

    marginal_fuel = None
    marginal_cost_jpy_mwh = None
    marginal_fuel_price_jpy_mmbtu = None
    price_status = "market_clearing"

    if shortage:
        marginal_fuel = "unserved_energy"
        marginal_cost_jpy_mwh = PRICE_CAP_JPY_MWH
        price_status = "price_cap_shortage"
    elif oversupplied:
        marginal_fuel = "renewable_curtailment"
        marginal_cost_jpy_mwh = 0.0
        price_status = "price_floor_oversupply"
    else:
        dispatched_rows = merit[
            merit["fuel_type"].map(dispatch_by_fuel).fillna(0.0) > EPSILON
        ]
        if not dispatched_rows.empty:
            marginal_row = dispatched_rows.iloc[-1]
            marginal_fuel = str(marginal_row["fuel_type"])
            marginal_cost_jpy_mwh = float(marginal_row["marginal_cost_jpy_mwh"])
            marginal_fuel_price_jpy_mmbtu = float(marginal_row["fuel_price_jpy_mmbtu"])

    clearing_price_jpy_mwh = determine_clearing_price(
        marginal_cost_jpy_mwh,
        oversupplied=oversupplied,
        shortage=shortage,
    )

    renewable_dispatched_mw = sum(
        dispatch_by_fuel.get(fuel, 0.0) for fuel in RENEWABLE_FUELS
    )
    dispatchable_generation_mw = (
        total_generation_mw - renewable_dispatched_mw - nuclear_output_mw
    )

    dispatch_rows: list[dict[str, object]] = []
    for fleet_row in merit.itertuples(index=False):
        fuel = fleet_row.fuel_type
        available_mw = float(available_by_fuel[fuel])
        dispatched_mw = float(dispatch_by_fuel[fuel])
        curtailed_mw = float(curtailed_by_fuel.get(fuel, 0.0))

        dispatch_rows.append(
            {
                "timestamp": row["timestamp"],
                "interval_hours": interval_hours,
                "fuel_type": fuel,
                "dispatch_group": fleet_row.dispatch_group,
                "merit_order_rank": int(fleet_row.merit_order_rank),
                "installed_capacity_mw": float(fleet_row.installed_capacity_mw),
                "available_mw": available_mw,
                "dispatched_mw": dispatched_mw,
                "dispatched_mwh": dispatched_mw * interval_hours,
                "curtailed_mw": curtailed_mw,
                "curtailed_mwh": curtailed_mw * interval_hours,
                "unused_available_mw": max(available_mw - dispatched_mw, 0.0),
                "utilization_pct_of_available": (
                    dispatched_mw / available_mw if available_mw > EPSILON else 0.0
                ),
                "fuel_price_jpy_mmbtu": float(fleet_row.fuel_price_jpy_mmbtu),
                "fuel_price_source": fleet_row.fuel_price_source,
                "heat_rate_mmbtu_per_mwh": float(fleet_row.heat_rate_mmbtu_per_mwh),
                "variable_om_jpy_mwh": float(fleet_row.variable_om_jpy_mwh),
                "marginal_cost_jpy_mwh": float(fleet_row.marginal_cost_jpy_mwh),
                "is_marginal_fleet": bool(
                    marginal_fuel == fuel and not oversupplied and not shortage
                ),
            }
        )

    summary_row: dict[str, object] = {
        "timestamp": row["timestamp"],
        "interval_hours": interval_hours,
        "demand_mw": demand_mw,
        "demand_mwh": demand_mw * interval_hours,
        "renewable_available_mw": sum(renewable_available.values()),
        "renewable_dispatched_mw": renewable_dispatched_mw,
        "renewable_curtailment_mw": renewable_curtailment_mw,
        "renewable_curtailment_mwh": renewable_curtailment_mw * interval_hours,
        "nuclear_dispatched_mw": nuclear_output_mw,
        "residual_demand_after_renewables_and_nuclear_mw": max(
            demand_mw - (sum(renewable_available.values()) + nuclear_output_mw),
            0.0,
        ),
        "dispatchable_generation_mw": dispatchable_generation_mw,
        "total_generation_mw": total_generation_mw,
        "total_generation_mwh": total_generation_mw * interval_hours,
        "noncurtailable_oversupply_mw": noncurtailable_oversupply_mw,
        "generation_minus_demand_mw": total_generation_mw - demand_mw,
        "unserved_energy_mw": unserved_energy_mw,
        "unserved_energy_mwh": unserved_energy_mw * interval_hours,
        "balance_with_unserved_mw": total_generation_mw
        + unserved_energy_mw
        - demand_mw,
        "marginal_fuel": marginal_fuel,
        "marginal_cost_jpy_mwh": marginal_cost_jpy_mwh,
        "marginal_fuel_price_jpy_mmbtu": marginal_fuel_price_jpy_mmbtu,
        "clearing_price_jpy_mwh": clearing_price_jpy_mwh,
        "clearing_price_jpy_kwh": clearing_price_jpy_mwh / 1000.0,
        "price_status": price_status,
    }

    if "actual_system_price_jpy_mwh" in row:
        summary_row["actual_system_price_jpy_mwh"] = row["actual_system_price_jpy_mwh"]
        summary_row["actual_system_price_jpy_kwh"] = (
            None
            if pd.isna(row["actual_system_price_jpy_mwh"])
            else float(row["actual_system_price_jpy_mwh"]) / 1000.0
        )

    if "actual_tokyo_price_jpy_mwh" in row:
        summary_row["actual_tokyo_price_jpy_mwh"] = row["actual_tokyo_price_jpy_mwh"]
        summary_row["actual_tokyo_price_jpy_kwh"] = (
            None
            if pd.isna(row["actual_tokyo_price_jpy_mwh"])
            else float(row["actual_tokyo_price_jpy_mwh"]) / 1000.0
        )

    return dispatch_rows, summary_row


def run_level1_dispatch(
    inputs: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run Level 1 dispatch using already-loaded processed inputs."""
    fleet_df = inputs["fleet"].copy()
    model_df = _prepare_model_table(inputs)
    interval_hours = _infer_interval_hours(model_df["timestamp"])

    required_fuels = {"solar", "wind", "nuclear"}
    missing_fuels = required_fuels.difference(set(fleet_df["fuel_type"]))
    if missing_fuels:
        raise ValueError(
            f"fleet.csv is missing required Level 1 fuels: {sorted(missing_fuels)}"
        )

    all_dispatch_rows: list[dict[str, object]] = []
    all_summary_rows: list[dict[str, object]] = []

    for row in model_df.itertuples(index=False):
        dispatch_rows, summary_row = _solve_single_timestamp(
            row._asdict(),
            fleet_df=fleet_df,
            interval_hours=interval_hours,
        )
        all_dispatch_rows.extend(dispatch_rows)
        all_summary_rows.append(summary_row)

    dispatch_df = (
        pd.DataFrame(all_dispatch_rows)
        .sort_values(["timestamp", "merit_order_rank"])
        .reset_index(drop=True)
    )
    summary_df = (
        pd.DataFrame(all_summary_rows).sort_values("timestamp").reset_index(drop=True)
    )
    return dispatch_df, summary_df


def run_level1_dispatch_from_processed(
    project_root: str | Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convenience wrapper to run Level 1 dispatch directly from processed CSVs."""
    inputs = load_processed_inputs(project_root=project_root)
    return run_level1_dispatch(inputs)


def write_level1_results(
    dispatch_df: pd.DataFrame,
    price_df: pd.DataFrame,
    project_root: str | Path | None = None,
    dispatch_filename: str = "base_dispatch.csv",
    prices_filename: str = "base_prices.csv",
) -> tuple[Path, Path]:
    """Write Level 1 outputs to output/results/."""
    root = _resolve_project_root(project_root)
    output_dir = root / "output" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    dispatch_path = output_dir / dispatch_filename
    prices_path = output_dir / prices_filename

    dispatch_df.to_csv(dispatch_path, index=False)
    price_df.to_csv(prices_path, index=False)

    return dispatch_path, prices_path


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Run Level 1 simple merit-order dispatch."
    )
    parser.add_argument(
        "--project-root",
        default=None,
        help="Project root path. Defaults to repository root inferred from this file.",
    )
    args = parser.parse_args()

    dispatch_df, price_df = run_level1_dispatch_from_processed(
        project_root=args.project_root
    )
    dispatch_path, prices_path = write_level1_results(
        dispatch_df=dispatch_df,
        price_df=price_df,
        project_root=args.project_root,
    )

    print(f"Wrote dispatch results to: {dispatch_path}")
    print(f"Wrote price results to:    {prices_path}")
    print(f"Timestamps solved:         {len(price_df):,}")
    print(f"Dispatch rows written:     {len(dispatch_df):,}")


if __name__ == "__main__":
    main()
