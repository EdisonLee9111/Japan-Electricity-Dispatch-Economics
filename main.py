"""Japan Electricity Dispatch Economics — main pipeline entry point.

Usage
-----
    python main.py                    # run full pipeline (base case)
    python main.py --steps load       # only load & validate inputs
    python main.py --steps dispatch   # load + dispatch
    python main.py --steps charts     # load + dispatch + charts
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


def run_pipeline(up_to: str = "backtest") -> None:
    """Execute the pipeline up to (and including) the given step."""
    settings = load_settings()
    print(f"=== {settings['project']['name']} v{settings['project']['version']} ===")
    print(f"    granularity : {settings['time']['granularity']}")
    print(f"    target price: {settings['backtest']['target_price']}")
    print(f"    spatial     : {settings['spatial']['model']}")
    print()

    cutoff = STEP_ORDER.index(up_to) if up_to in STEP_ORDER else len(STEP_ORDER) - 1

    # Step 1 — load
    inputs = load_inputs()

    # Step 2 — prepare fleet
    inputs = prepare_fleet(inputs)

    if cutoff < 1:
        return

    # Step 3 — dispatch
    dispatch_df, price_df = run_base_dispatch(inputs)

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
    args = parser.parse_args()

    try:
        run_pipeline(up_to=args.steps)
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
