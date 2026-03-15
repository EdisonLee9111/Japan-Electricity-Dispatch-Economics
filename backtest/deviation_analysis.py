"""Deviation analysis — when and why the model diverges from JEPX actuals.

Breaks down forecast errors by time-of-day, month, and price regime to
help explain systematic deviations attributable to the model's simplifying
assumptions (copper-plate, competitive bidding, perfect foresight, etc.).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def analyse_deviations(
    prices_df: pd.DataFrame,
    simulated_col: str = "clearing_price_jpy_kwh",
    actual_col: str = "actual_system_price_jpy_kwh",
) -> dict | None:
    """Produce structured deviation analysis.

    Returns None if actual prices are not available.
    """
    if actual_col not in prices_df.columns:
        return None

    df = prices_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    valid = df.dropna(subset=[simulated_col, actual_col]).copy()
    if valid.empty:
        return None

    valid["error"] = valid[simulated_col] - valid[actual_col]
    valid["abs_error"] = valid["error"].abs()
    valid["hour"] = valid["timestamp"].dt.hour
    valid["month"] = valid["timestamp"].dt.month
    valid["dow"] = valid["timestamp"].dt.dayofweek

    # By hour
    hourly = valid.groupby("hour")["error"].agg(["mean", "std", "count"])
    hourly.columns = ["mean_error", "std_error", "count"]

    # By month
    monthly = valid.groupby("month")["error"].agg(["mean", "std", "count"])
    monthly.columns = ["mean_error", "std_error", "count"]

    # By price regime
    actual_prices = valid[actual_col]
    q25, q75 = actual_prices.quantile(0.25), actual_prices.quantile(0.75)
    valid["regime"] = pd.cut(
        actual_prices,
        bins=[-np.inf, q25, q75, np.inf],
        labels=["low", "mid", "high"],
    )
    regime = valid.groupby("regime", observed=True)["error"].agg(["mean", "std", "count"])
    regime.columns = ["mean_error", "std_error", "count"]

    # By marginal fuel
    if "marginal_fuel" in valid.columns:
        by_fuel = valid.groupby("marginal_fuel")["error"].agg(["mean", "std", "count"])
        by_fuel.columns = ["mean_error", "std_error", "count"]
    else:
        by_fuel = pd.DataFrame()

    # Worst hours (largest absolute errors)
    worst = valid.nlargest(20, "abs_error")[
        ["timestamp", simulated_col, actual_col, "error", "marginal_fuel"]
    ].copy() if "marginal_fuel" in valid.columns else valid.nlargest(20, "abs_error")[
        ["timestamp", simulated_col, actual_col, "error"]
    ].copy()

    return {
        "by_hour": hourly,
        "by_month": monthly,
        "by_regime": regime,
        "by_marginal_fuel": by_fuel,
        "worst_20_timestamps": worst,
    }


def print_deviation_report(analysis: dict) -> None:
    """Print a human-readable deviation report."""
    print("\n" + "=" * 60)
    print("BACKTEST DEVIATION ANALYSIS")
    print("=" * 60)

    print("\n--Error by Hour of Day --")
    print(analysis["by_hour"].to_string(float_format="{:.3f}".format))

    print("\n--Error by Month --")
    print(analysis["by_month"].to_string(float_format="{:.3f}".format))

    print("\n--Error by Price Regime --")
    print(analysis["by_regime"].to_string(float_format="{:.3f}".format))

    if not analysis["by_marginal_fuel"].empty:
        print("\n--Error by Marginal Fuel --")
        print(analysis["by_marginal_fuel"].to_string(float_format="{:.3f}".format))

    print("\n--Top 20 Worst Forecast Errors --")
    print(analysis["worst_20_timestamps"].to_string(index=False))

    print("\n-- Model Limitation Notes --")
    print("  1. Copper-plate: no regional transmission constraints modeled")
    print("  2. Competitive bidding: assumes marginal cost bidding (no strategic bids)")
    print("  3. Perfect foresight: uses actual RE output, not forecasts")
    print("  4. No demand response or storage arbitrage")
    print("  5. Single day-ahead market; real-time balancing ignored")
    print("=" * 60)


def write_deviation_report(
    analysis: dict,
    project_root: str | Path | None = None,
) -> list[Path]:
    """Write deviation analysis tables to CSV."""
    if project_root is None:
        root = Path(__file__).resolve().parents[1]
    else:
        root = Path(project_root).resolve()

    output_dir = root / "output" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []

    for key in ("by_hour", "by_month", "by_regime", "by_marginal_fuel"):
        df = analysis.get(key)
        if df is not None and not df.empty:
            path = output_dir / f"backtest_deviation_{key}.csv"
            df.to_csv(path)
            written.append(path)

    worst = analysis.get("worst_20_timestamps")
    if worst is not None and not worst.empty:
        path = output_dir / "backtest_worst_errors.csv"
        worst.to_csv(path, index=False)
        written.append(path)

    return written
