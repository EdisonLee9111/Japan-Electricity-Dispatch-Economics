"""Price comparison — orchestrates backtest metrics and deviation analysis."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .metrics import compute_metrics
from .deviation_analysis import analyse_deviations, print_deviation_report, write_deviation_report


def run_backtest(
    prices_df: pd.DataFrame,
    *,
    verbose: bool = True,
    project_root: str | Path | None = None,
) -> dict | None:
    """Run full backtest: metrics + deviation analysis.

    Returns None if actual JEPX prices are not available.
    """
    metrics = compute_metrics(prices_df)
    if metrics is None:
        if verbose:
            print("  Backtest skipped: no actual JEPX prices in results.")
        return None

    if verbose:
        print(f"  Backtest metrics (N={metrics['n_observations']:,}):")
        print(f"    RMSE:  {metrics['rmse_jpy_kwh']:.3f} JPY/kWh")
        print(f"    MAE:   {metrics['mae_jpy_kwh']:.3f} JPY/kWh")
        print(f"    Bias:  {metrics['bias_jpy_kwh']:+.3f} JPY/kWh")
        print(f"    R2:    {metrics['r_squared']:.4f}")
        print(f"    Corr:  {metrics['correlation']:.4f}")

    analysis = analyse_deviations(prices_df)

    if verbose and analysis is not None:
        print_deviation_report(analysis)

    written: list[Path] = []
    if analysis is not None and project_root is not None:
        written = write_deviation_report(analysis, project_root=project_root)

    return {
        "metrics": metrics,
        "analysis": analysis,
        "written_files": written,
    }
