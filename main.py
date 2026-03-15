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


def run_scenarios(dispatch_df, price_df) -> None:
    """Phase 4 — scenario engine (placeholder)."""
    print("[4/6] Scenario engine … (not yet implemented, skipping)")


def generate_charts(dispatch_df, price_df) -> None:
    """Phase 5 — visualization (placeholder)."""
    print("[5/6] Chart generation … (not yet implemented, skipping)")


def run_backtest(price_df) -> None:
    """Phase 6 — backtest against JEPX (placeholder)."""
    print("[6/6] Backtest … (not yet implemented, skipping)")


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

    # Step 4 — scenarios (placeholder)
    run_scenarios(dispatch_df, price_df)

    # Step 5 — charts (placeholder)
    generate_charts(dispatch_df, price_df)

    if cutoff < 4:
        return

    # Step 6 — backtest (placeholder)
    run_backtest(price_df)

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
