"""Japan Electricity Dispatch Economics — main pipeline entry point.

Usage
-----
    python main.py                    # run full pipeline (base case)
    python main.py --steps load       # only load & validate inputs
    python main.py --steps dispatch   # load + dispatch (Level 1 + Level 2 UC)
    python main.py --steps charts     # load + dispatch + charts
    python main.py --uc-hours 24      # UC window size (default: 168 = 1 week)
    python main.py --no-uc            # skip Level 2 UC solver
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent

# ── helpers ───────────────────────────────────────────────────────────────────

def _elapsed(start: float) -> str:
    return f"{time.time() - start:.1f}s"


def load_settings() -> dict:
    """Load project settings from config/settings.yaml."""
    settings_path = PROJECT_ROOT / "config" / "settings.yaml"
    with open(settings_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── pipeline steps ────────────────────────────────────────────────────────────

def load_inputs() -> dict:
    """Phase 1 — load and validate all processed inputs."""
    from engine.dispatch_solver import load_processed_inputs

    print("[1/6] Loading processed inputs …")
    t0 = time.time()
    inputs = load_processed_inputs(project_root=PROJECT_ROOT)

    for name, df in inputs.items():
        print(f"      {name:25s}  {len(df):>7,} rows  ×  {len(df.columns)} cols")
    print(f"      done ({_elapsed(t0)})")
    return inputs


def prepare_fleet(inputs: dict) -> dict:
    """Phase 1 supplement — any fleet pre-processing before dispatch."""
    print("[2/6] Preparing fleet …")
    fleet = inputs["fleet"]
    print(f"      {len(fleet)} fleet entries: {', '.join(fleet['fuel_type'].tolist())}")
    return inputs


def run_base_dispatch(inputs: dict) -> tuple:
    """Phase 2 — run Level 1 simple merit-order dispatch."""
    from engine.dispatch_solver import run_level1_dispatch, write_level1_results

    print("[3/6] Running Level 1 base dispatch …")
    t0 = time.time()
    dispatch_df, price_df = run_level1_dispatch(inputs)

    dispatch_path, prices_path = write_level1_results(
        dispatch_df, price_df, project_root=PROJECT_ROOT
    )

    print(f"      timestamps solved: {len(price_df):,}")
    print(f"      dispatch rows:     {len(dispatch_df):,}")
    print(f"      → {dispatch_path.relative_to(PROJECT_ROOT)}")
    print(f"      → {prices_path.relative_to(PROJECT_ROOT)}")
    print(f"      done ({_elapsed(t0)})")
    return dispatch_df, price_df


def run_unit_commitment(inputs: dict, uc_hours: int = 168) -> tuple | None:
    """Phase 3 — run Level 2 LP/MILP unit commitment on a representative window."""
    from engine.uc_solver import run_unit_commitment as _run_uc, write_uc_results

    print(f"[3b/6] Running Level 2 UC ({uc_hours}h window) …")
    t0 = time.time()
    dispatch_df, summary_df, solve_info = _run_uc(
        inputs, hours=uc_hours, time_limit_seconds=600, msg=True
    )

    if solve_info["status"] != "Optimal":
        print(f"      WARNING: solver status = {solve_info['status']}")
        print(f"      done ({_elapsed(t0)})")
        return None

    dispatch_path, prices_path = write_uc_results(
        dispatch_df, summary_df, project_root=PROJECT_ROOT, suffix=f"{uc_hours}h"
    )

    print(f"      timestamps solved: {len(summary_df):,}")
    print(f"      dispatch rows:     {len(dispatch_df):,}")
    print(f"      startups: {dispatch_df[dispatch_df['startup'] > 0].groupby('fuel_type')['startup'].sum().to_dict()}")
    print(f"      → {dispatch_path.relative_to(PROJECT_ROOT)}")
    print(f"      → {prices_path.relative_to(PROJECT_ROOT)}")
    print(f"      done ({_elapsed(t0)})")
    return dispatch_df, summary_df


def run_scenarios(inputs: dict) -> dict | None:
    """Phase 4 — scenario engine: run all scenarios and compare vs base."""
    from scenarios.runner import run_all_scenarios, write_scenario_results
    from scenarios.comparator import compare_all, print_comparison_report, write_comparison

    print("[4/6] Running scenario engine …")
    t0 = time.time()

    results = run_all_scenarios(inputs, verbose=True)
    written = write_scenario_results(results, project_root=PROJECT_ROOT)

    summary_table, deltas = compare_all(results, base_name="base")
    print_comparison_report(summary_table, deltas)
    comparison_files = write_comparison(summary_table, deltas, project_root=PROJECT_ROOT)
    written.extend(comparison_files)

    for p in written:
        print(f"      → {p.relative_to(PROJECT_ROOT)}")
    print(f"      done ({_elapsed(t0)})")

    return results


def generate_charts(
    dispatch_df,
    price_df,
    inputs: dict,
    scenario_results: dict | None = None,
) -> None:
    """Phase 5 — generate all 7 chart types."""
    import matplotlib
    matplotlib.use("Agg")  # non-interactive backend for file output

    from visualization import (
        plot_merit_order,
        plot_duck_curve,
        plot_seasonal_heatmap,
        plot_marginal_fuel_heatmap,
        plot_dispatch_stack,
        plot_price_duration,
        plot_scenario_comparison,
        plot_backtest,
    )

    print("[5/6] Generating charts …")
    t0 = time.time()
    charts_dir = PROJECT_ROOT / "output" / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    # Chart 1: Merit order curve (use first timestamp's fuel prices)
    fuel_row = inputs["fuel_prices"].iloc[0].to_dict()
    plot_merit_order(
        inputs["fleet"],
        fuel_prices_row=fuel_row,
        output_path=charts_dir / "01_merit_order_curve.png",
    )
    print("      → 01_merit_order_curve.png")

    # Chart 2: Duck curve
    plot_duck_curve(
        price_df,
        dispatch_df,
        output_path=charts_dir / "02_duck_curve.png",
    )
    print("      → 02_duck_curve.png")

    # Chart 3a: Seasonal heatmap (clearing price)
    plot_seasonal_heatmap(
        price_df,
        output_path=charts_dir / "03a_seasonal_price_heatmap.png",
    )
    print("      → 03a_seasonal_price_heatmap.png")

    # Chart 3b: Seasonal heatmap (marginal fuel)
    plot_marginal_fuel_heatmap(
        price_df,
        output_path=charts_dir / "03b_marginal_fuel_heatmap.png",
    )
    print("      → 03b_marginal_fuel_heatmap.png")

    # Chart 4: Dispatch stack (representative days)
    plot_dispatch_stack(
        price_df,
        dispatch_df,
        output_path=charts_dir / "04_dispatch_stack.png",
    )
    print("      → 04_dispatch_stack.png")

    # Chart 5: Price duration curve
    prices_dict = {"base": price_df}
    if scenario_results:
        for name, res in scenario_results.items():
            if name != "base":
                prices_dict[name] = res["prices"]
    plot_price_duration(
        prices_dict,
        output_path=charts_dir / "05_price_duration_curve.png",
    )
    print("      → 05_price_duration_curve.png")

    # Chart 6: Scenario comparison dashboard
    if scenario_results:
        from scenarios.comparator import compare_all
        summary_table, _ = compare_all(scenario_results, base_name="base")
        plot_scenario_comparison(
            summary_table,
            output_path=charts_dir / "06_scenario_comparison.png",
        )
        print("      → 06_scenario_comparison.png")

    # Chart 7: Backtest
    fig = plot_backtest(
        price_df,
        output_path=charts_dir / "07_backtest.png",
    )
    if fig is not None:
        print("      → 07_backtest.png")
    else:
        print("      → 07_backtest.png (skipped — no actual JEPX prices)")

    print(f"      done ({_elapsed(t0)})")


def run_backtest_phase(price_df) -> None:
    """Phase 6 — backtest against JEPX actuals."""
    from backtest.price_comparison import run_backtest as _run_backtest

    print("[6/6] Running backtest …")
    t0 = time.time()
    result = _run_backtest(price_df, verbose=True, project_root=PROJECT_ROOT)

    if result is None:
        print("      Backtest skipped — no actual JEPX prices available.")
    else:
        for p in result.get("written_files", []):
            print(f"      → {p.relative_to(PROJECT_ROOT)}")

    print(f"      done ({_elapsed(t0)})")


# ── orchestrator ──────────────────────────────────────────────────────────────

STEP_ORDER = ["load", "dispatch", "charts", "scenarios", "backtest"]


def run_pipeline(up_to: str = "backtest", uc_hours: int = 168, skip_uc: bool = False) -> None:
    """Execute the pipeline up to (and including) the given step."""
    settings = load_settings()
    print(f"=== {settings['project']['name']} v{settings['project']['version']} ===")
    print(f"    granularity : {settings['time']['granularity']}")
    print(f"    target price: {settings['backtest']['target_price']}")
    print(f"    spatial     : {settings['spatial']['model']}")
    print(f"    UC solver   : {'OFF' if skip_uc else f'{uc_hours}h window'}")
    print()

    cutoff = STEP_ORDER.index(up_to) if up_to in STEP_ORDER else len(STEP_ORDER) - 1

    # Step 1 — load
    inputs = load_inputs()

    # Step 2 — prepare fleet
    inputs = prepare_fleet(inputs)

    if cutoff < 1:
        return

    # Step 3a — Level 1 dispatch
    dispatch_df, price_df = run_base_dispatch(inputs)

    # Step 3b — Level 2 UC (optional)
    if not skip_uc:
        run_unit_commitment(inputs, uc_hours=uc_hours)

    if cutoff < 2:
        return

    # Step 4 — scenarios
    scenario_results = run_scenarios(inputs)

    # Step 5 — charts
    generate_charts(dispatch_df, price_df, inputs, scenario_results)

    if cutoff < 4:
        return

    # Step 6 — backtest
    run_backtest_phase(price_df)

    print()
    print("Pipeline complete.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Japan Electricity Dispatch Economics — run the analysis pipeline."
    )
    parser.add_argument(
        "--steps",
        choices=STEP_ORDER,
        default="backtest",
        help="Run pipeline up to this step (default: full pipeline).",
    )
    parser.add_argument(
        "--uc-hours",
        type=int,
        default=168,
        help="UC window size in hours (default: 168 = 1 week).",
    )
    parser.add_argument(
        "--no-uc",
        action="store_true",
        help="Skip Level 2 UC solver.",
    )
    args = parser.parse_args()

    try:
        run_pipeline(up_to=args.steps, uc_hours=args.uc_hours, skip_uc=args.no_uc)
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
