"""Level 2 LP/MILP Unit Commitment solver using PuLP.

This module implements a simplified unit commitment formulation that captures
inter-temporal constraints missing from the Level 1 merit-order dispatch:

- Startup costs (hot / warm / cold, simplified to cold-start in LP)
- Minimum stable generation (online units must produce >= min_stable_pct * capacity)
- Minimum up time / down time
- Ramp rate constraints between consecutive hours

The solver operates on a time window (e.g. 24h, 72h, 168h) and finds the
cost-minimising generation schedule subject to physical constraints.

Key simplification vs. full MILP:
- Fleet-level aggregation (not individual plants)
- Startup cost uses cold-start cost as upper bound (conservative)
- Binary commitment variables for each fleet × hour
- Single-node copper-plate (no transmission)

Requires: pip install pulp
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import pulp

try:
    from .merit_order import MUST_RUN_FUELS, RENEWABLE_FUELS, build_merit_order
    from .dispatch_solver import load_processed_inputs, _prepare_model_table, _infer_interval_hours
except ImportError:
    from merit_order import MUST_RUN_FUELS, RENEWABLE_FUELS, build_merit_order
    from dispatch_solver import load_processed_inputs, _prepare_model_table, _infer_interval_hours


# Fleets that participate in UC (have on/off decisions)
UC_FUEL_TYPES = {"coal_usc", "coal_old", "lng_ccgt", "lng_ocgt", "oil", "biomass", "hydro"}

# Fleets dispatched outside UC (fixed or must-take)
FIXED_FUEL_TYPES = RENEWABLE_FUELS | MUST_RUN_FUELS


def _resolve_project_root(project_root: str | Path | None = None) -> Path:
    if project_root is None:
        return Path(__file__).resolve().parents[1]
    return Path(project_root).resolve()


def _extract_window(
    model_df: pd.DataFrame,
    start: str | pd.Timestamp | None = None,
    hours: int = 24,
    interval_hours: float = 1.0,
) -> pd.DataFrame:
    """Extract a time window from the model table.

    Parameters
    ----------
    hours : int
        Duration of the window in actual hours.
    interval_hours : float
        Length of each timestamp interval in hours (e.g. 0.5 for 30-min data).
    """
    df = model_df.sort_values("timestamp").reset_index(drop=True)
    if start is not None:
        start_ts = pd.Timestamp(start)
        df = df[df["timestamp"] >= start_ts].reset_index(drop=True)
    n_steps = int(hours / interval_hours)
    if len(df) > n_steps:
        df = df.iloc[:n_steps].copy()
    return df.reset_index(drop=True)


def run_unit_commitment(
    inputs: dict[str, pd.DataFrame],
    start: str | pd.Timestamp | None = None,
    hours: int = 24,
    time_limit_seconds: int = 300,
    msg: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Run Level 2 unit commitment for a given time window.

    Parameters
    ----------
    inputs : dict
        Processed inputs from load_processed_inputs().
    start : str or Timestamp, optional
        Start of the window. If None, uses first available timestamp.
    hours : int
        Number of hours in the window (default 24).
    time_limit_seconds : int
        Solver time limit.
    msg : bool
        Print solver messages.

    Returns
    -------
    dispatch_df : DataFrame
        Per-fleet per-hour dispatch results.
    summary_df : DataFrame
        Per-hour summary with prices and balances.
    solve_info : dict
        Solver status, objective value, timing.
    """
    fleet_df = inputs["fleet"].copy()
    model_df = _prepare_model_table(inputs)
    interval_hours = _infer_interval_hours(model_df["timestamp"])
    window = _extract_window(model_df, start=start, hours=hours, interval_hours=interval_hours)

    T = len(window)  # number of time steps
    timestamps = window["timestamp"].tolist()

    if msg:
        print(f"  UC window: {timestamps[0]} → {timestamps[-1]} ({T} steps)")

    # ── Identify fleets ──────────────────────────────────────────────────────
    # Build merit order for the first timestamp to get marginal costs
    first_row = window.iloc[0].to_dict()
    merit = build_merit_order(fleet_df, first_row)

    # Separate UC-eligible and fixed fleets
    uc_fleets = merit[merit["fuel_type"].isin(UC_FUEL_TYPES)].copy()
    fixed_fleets = merit[merit["fuel_type"].isin(FIXED_FUEL_TYPES)].copy()

    uc_fuel_list = uc_fleets["fuel_type"].tolist()
    N_uc = len(uc_fuel_list)

    # Fleet parameters (indexed by fuel_type)
    # Fleet-level ramp rate scaling: the ramp rates in fleet.csv are per-unit
    # values, but we model aggregated fleets with many independent units that
    # can ramp simultaneously.  Use max(csv_ramp, 20% of capacity/hr) as a
    # practical fleet-level approximation.
    FLEET_RAMP_FLOOR_PCT = 0.20

    fleet_params = {}
    for _, row in fleet_df.iterrows():
        ft = row["fuel_type"]
        cap = float(row["installed_capacity_mw"])
        csv_ramp = float(row["ramp_rate_mw_per_hour"])
        fleet_ramp = max(csv_ramp, FLEET_RAMP_FLOOR_PCT * cap)
        fleet_params[ft] = {
            "capacity_mw": cap,
            "min_stable_pct": float(row["min_stable_generation_pct"]),
            "min_stable_mw": cap * float(row["min_stable_generation_pct"]),
            "heat_rate": float(row["heat_rate_mmbtu_per_mwh"]),
            "var_om": float(row["variable_om_jpy_mwh"]),
            "startup_cold_jpy_per_mw": float(row["startup_cost_cold_jpy_per_mw"]),
            "min_up_time": int(row["min_up_time_hours"]),
            "min_down_time": int(row["min_down_time_hours"]),
            "ramp_rate": fleet_ramp,
        }

    # ── Pre-compute time-varying marginal costs for UC fleets ────────────────
    # marginal_cost[fuel][t] = fuel_price * heat_rate + var_om
    marginal_costs = {}
    for t_idx in range(T):
        row_dict = window.iloc[t_idx].to_dict()
        mo = build_merit_order(fleet_df, row_dict)
        for _, mo_row in mo.iterrows():
            ft = mo_row["fuel_type"]
            if ft in UC_FUEL_TYPES:
                if ft not in marginal_costs:
                    marginal_costs[ft] = {}
                marginal_costs[ft][t_idx] = float(mo_row["marginal_cost_jpy_mwh"])

    # ── Pre-compute fixed generation (renewables, nuclear, hydro) ────────────
    fixed_gen = {}  # fixed_gen[t] = total fixed generation MW
    renewable_gen = {}  # renewable_gen[fuel][t] = MW
    for t_idx in range(T):
        row_dict = window.iloc[t_idx].to_dict()
        total_fixed = 0.0
        for _, fr in fixed_fleets.iterrows():
            ft = fr["fuel_type"]
            cap = float(fr["installed_capacity_mw"])
            if ft == "solar":
                gen = cap * float(row_dict.get("solar_cf", 0.0))
            elif ft == "wind":
                gen = cap * float(row_dict.get("wind_cf", 0.0))
            elif ft == "nuclear":
                gen = cap  # must-run at full capacity
            else:
                gen = 0.0
            if ft not in renewable_gen:
                renewable_gen[ft] = {}
            renewable_gen[ft][t_idx] = gen
            total_fixed += gen
        fixed_gen[t_idx] = total_fixed

    # ── Build LP/MILP problem ────────────────────────────────────────────────
    prob = pulp.LpProblem("UnitCommitment", pulp.LpMinimize)

    # Decision variables
    # gen[fuel][t] = generation MW (continuous)
    gen = {}
    # u[fuel][t] = online status (binary: 1=on, 0=off)
    u = {}
    # v[fuel][t] = startup indicator (binary: 1=started up at t)
    v = {}
    # curtailment[t] = renewable curtailment MW (continuous, >= 0)
    curtail = {}
    # unserved[t] = unserved energy MW (continuous, >= 0)
    unserved = {}

    for fuel in uc_fuel_list:
        gen[fuel] = {}
        u[fuel] = {}
        v[fuel] = {}
        cap = fleet_params[fuel]["capacity_mw"]
        for t in range(T):
            gen[fuel][t] = pulp.LpVariable(
                f"gen_{fuel}_{t}", lowBound=0, upBound=cap, cat="Continuous"
            )
            u[fuel][t] = pulp.LpVariable(
                f"u_{fuel}_{t}", cat="Binary"
            )
            v[fuel][t] = pulp.LpVariable(
                f"v_{fuel}_{t}", cat="Binary"
            )

    for t in range(T):
        curtail[t] = pulp.LpVariable(f"curtail_{t}", lowBound=0, cat="Continuous")
        unserved[t] = pulp.LpVariable(f"unserved_{t}", lowBound=0, cat="Continuous")

    # ── Objective: minimize total cost ───────────────────────────────────────
    # Cost = Σ generation_cost + Σ startup_cost + Σ penalty_for_unserved
    VOLL = 100_000.0  # Value of Lost Load (JPY/MWh) — penalty for unserved

    obj = []
    for fuel in uc_fuel_list:
        cap = fleet_params[fuel]["capacity_mw"]
        startup_cost_total = fleet_params[fuel]["startup_cold_jpy_per_mw"] * cap
        for t in range(T):
            # Variable generation cost
            mc = marginal_costs[fuel][t]
            obj.append(mc * interval_hours * gen[fuel][t])
            # Startup cost
            obj.append(startup_cost_total * v[fuel][t])

    # Unserved energy penalty
    for t in range(T):
        obj.append(VOLL * interval_hours * unserved[t])

    prob += pulp.lpSum(obj), "TotalCost"

    # ── Constraints ──────────────────────────────────────────────────────────

    for t in range(T):
        demand_mw = float(window.iloc[t]["demand_mw"])
        fixed_mw = fixed_gen[t]

        # 1. Demand balance: fixed_gen - curtailment + Σ uc_gen + unserved = demand
        prob += (
            pulp.lpSum(gen[fuel][t] for fuel in uc_fuel_list)
            + fixed_mw
            - curtail[t]
            + unserved[t]
            == demand_mw,
            f"demand_balance_{t}",
        )

        # Curtailment cannot exceed fixed generation
        prob += curtail[t] <= fixed_mw, f"curtail_cap_{t}"

    for fuel in uc_fuel_list:
        cap = fleet_params[fuel]["capacity_mw"]
        min_gen = fleet_params[fuel]["min_stable_mw"]
        min_up = fleet_params[fuel]["min_up_time"]
        min_down = fleet_params[fuel]["min_down_time"]
        ramp = fleet_params[fuel]["ramp_rate"]

        for t in range(T):
            # 2. Capacity upper bound: gen <= capacity * u (online)
            prob += gen[fuel][t] <= cap * u[fuel][t], f"cap_upper_{fuel}_{t}"

            # 3. Minimum stable generation: gen >= min_stable * u (online)
            prob += gen[fuel][t] >= min_gen * u[fuel][t], f"min_stable_{fuel}_{t}"

            # 4. Startup indicator: v[t] >= u[t] - u[t-1]
            if t == 0:
                # Assume major fleets start online (realistic for base case)
                # Small/peaking fleets (OCGT, oil) start offline
                initial_online = 1 if fuel in {"coal_usc", "coal_old", "lng_ccgt", "biomass", "hydro"} else 0
                prob += (
                    v[fuel][t] >= u[fuel][t] - initial_online,
                    f"startup_{fuel}_{t}",
                )
            else:
                prob += (
                    v[fuel][t] >= u[fuel][t] - u[fuel][t - 1],
                    f"startup_{fuel}_{t}",
                )

            # 5. Minimum up time: if started at t, must stay on for min_up hours
            if min_up > 1:
                for tau in range(t + 1, min(t + min_up, T)):
                    prob += (
                        u[fuel][tau] >= v[fuel][t],
                        f"min_up_{fuel}_{t}_{tau}",
                    )

            # 6. Minimum down time: if shut down at t, must stay off for min_down hours
            if min_down > 1 and t > 0:
                # shutdown indicator: u[t-1] - u[t] >= 0 means shutdown at t
                # if shutdown at t, then u[tau] = 0 for tau in [t+1, t+min_down)
                for tau in range(t + 1, min(t + min_down, T)):
                    prob += (
                        u[fuel][tau] <= 1 - (u[fuel][t - 1] - u[fuel][t]),
                        f"min_down_{fuel}_{t}_{tau}",
                    )

            # 7. Ramp rate constraints
            if t > 0:
                prob += (
                    gen[fuel][t] - gen[fuel][t - 1] <= ramp * interval_hours,
                    f"ramp_up_{fuel}_{t}",
                )
                prob += (
                    gen[fuel][t - 1] - gen[fuel][t] <= ramp * interval_hours,
                    f"ramp_down_{fuel}_{t}",
                )

    # ── Solve ────────────────────────────────────────────────────────────────
    t0 = time.time()

    solver = pulp.PULP_CBC_CMD(
        msg=0 if not msg else 1,
        timeLimit=time_limit_seconds,
        gapRel=0.01,  # 1% optimality gap
    )
    status = prob.solve(solver)
    solve_time = time.time() - t0

    status_str = pulp.LpStatus[status]
    obj_value = pulp.value(prob.objective) if status == 1 else None

    if msg:
        print(f"  Solver status: {status_str}")
        print(f"  Objective value: {obj_value:,.0f} JPY" if obj_value else "  No solution")
        print(f"  Solve time: {solve_time:.1f}s")

    solve_info = {
        "status": status_str,
        "objective_value": obj_value,
        "solve_time_seconds": solve_time,
        "num_variables": prob.numVariables(),
        "num_constraints": prob.numConstraints(),
        "window_hours": T,
    }

    if status != 1:  # Not optimal
        return pd.DataFrame(), pd.DataFrame(), solve_info

    # ── Extract results ──────────────────────────────────────────────────────
    dispatch_rows = []
    summary_rows = []

    for t in range(T):
        ts = timestamps[t]
        demand_mw = float(window.iloc[t]["demand_mw"])
        row_dict = window.iloc[t].to_dict()

        curtail_mw = float(pulp.value(curtail[t]))
        unserved_mw = float(pulp.value(unserved[t]))

        total_gen = 0.0

        # Fixed fleets
        for ft in FIXED_FUEL_TYPES:
            if ft in renewable_gen and t in renewable_gen[ft]:
                gen_mw = renewable_gen[ft][t]
            else:
                gen_mw = 0.0

            # Subtract curtailment proportionally from renewables
            if ft in RENEWABLE_FUELS and curtail_mw > 0:
                total_re = sum(
                    renewable_gen.get(rf, {}).get(t, 0.0) for rf in RENEWABLE_FUELS
                )
                if total_re > 0:
                    curtail_share = gen_mw / total_re * curtail_mw
                    gen_mw_after = max(gen_mw - curtail_share, 0.0)
                else:
                    curtail_share = 0.0
                    gen_mw_after = gen_mw
            else:
                curtail_share = 0.0
                gen_mw_after = gen_mw

            dispatch_rows.append({
                "timestamp": ts,
                "fuel_type": ft,
                "dispatch_group": "renewable" if ft in RENEWABLE_FUELS else (
                    "must_run" if ft in MUST_RUN_FUELS else "fixed"
                ),
                "installed_capacity_mw": fleet_params.get(ft, {}).get("capacity_mw", 0.0)
                    if ft in fleet_params else float(
                        fleet_df.loc[fleet_df["fuel_type"] == ft, "installed_capacity_mw"].iloc[0]
                    ) if ft in fleet_df["fuel_type"].values else 0.0,
                "dispatched_mw": gen_mw_after,
                "dispatched_mwh": gen_mw_after * interval_hours,
                "curtailed_mw": curtail_share if ft in RENEWABLE_FUELS else 0.0,
                "online_status": 1,
                "startup": 0,
                "marginal_cost_jpy_mwh": 0.0,
            })
            total_gen += gen_mw_after

        # UC fleets
        marginal_fuel = None
        marginal_cost = 0.0

        for fuel in uc_fuel_list:
            gen_mw = float(pulp.value(gen[fuel][t]))
            online = int(round(float(pulp.value(u[fuel][t]))))
            started = int(round(float(pulp.value(v[fuel][t]))))
            mc = marginal_costs[fuel][t]
            cap = fleet_params[fuel]["capacity_mw"]

            dispatch_rows.append({
                "timestamp": ts,
                "fuel_type": fuel,
                "dispatch_group": "dispatchable",
                "installed_capacity_mw": cap,
                "dispatched_mw": gen_mw,
                "dispatched_mwh": gen_mw * interval_hours,
                "curtailed_mw": 0.0,
                "online_status": online,
                "startup": started,
                "marginal_cost_jpy_mwh": mc,
            })
            total_gen += gen_mw

            if gen_mw > 0.1 and mc > marginal_cost:
                marginal_cost = mc
                marginal_fuel = fuel

        # Summary row
        clearing_price = marginal_cost if marginal_fuel else 0.0
        if unserved_mw > 0.1:
            clearing_price = 99_990.0
            marginal_fuel = "unserved_energy"

        summary_row = {
            "timestamp": ts,
            "interval_hours": interval_hours,
            "demand_mw": demand_mw,
            "demand_mwh": demand_mw * interval_hours,
            "total_generation_mw": total_gen,
            "total_generation_mwh": total_gen * interval_hours,
            "curtailment_mw": curtail_mw,
            "curtailment_mwh": curtail_mw * interval_hours,
            "unserved_energy_mw": unserved_mw,
            "unserved_energy_mwh": unserved_mw * interval_hours,
            "marginal_fuel": marginal_fuel,
            "clearing_price_jpy_mwh": clearing_price,
            "clearing_price_jpy_kwh": clearing_price / 1000.0,
        }

        # Attach actual prices if available
        if "actual_system_price_jpy_mwh" in row_dict:
            summary_row["actual_system_price_jpy_mwh"] = row_dict["actual_system_price_jpy_mwh"]
        if "actual_tokyo_price_jpy_mwh" in row_dict:
            summary_row["actual_tokyo_price_jpy_mwh"] = row_dict["actual_tokyo_price_jpy_mwh"]

        summary_rows.append(summary_row)

    dispatch_df = pd.DataFrame(dispatch_rows).sort_values(
        ["timestamp", "fuel_type"]
    ).reset_index(drop=True)

    summary_df = pd.DataFrame(summary_rows).sort_values("timestamp").reset_index(drop=True)

    return dispatch_df, summary_df, solve_info


def run_uc_from_processed(
    project_root: str | Path | None = None,
    start: str | None = None,
    hours: int = 24,
    time_limit_seconds: int = 300,
    msg: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Convenience wrapper to run UC directly from processed CSVs."""
    inputs = load_processed_inputs(project_root=project_root)
    return run_unit_commitment(
        inputs, start=start, hours=hours,
        time_limit_seconds=time_limit_seconds, msg=msg,
    )


def write_uc_results(
    dispatch_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    project_root: str | Path | None = None,
    suffix: str = "",
) -> tuple[Path, Path]:
    """Write UC results to output/results/."""
    root = _resolve_project_root(project_root)
    output_dir = root / "output" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    tag = f"_{suffix}" if suffix else ""
    dispatch_path = output_dir / f"uc_dispatch{tag}.csv"
    summary_path = output_dir / f"uc_prices{tag}.csv"

    dispatch_df.to_csv(dispatch_path, index=False)
    summary_df.to_csv(summary_path, index=False)

    return dispatch_path, summary_path
