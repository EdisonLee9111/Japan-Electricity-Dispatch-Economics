"""Backtest metrics — RMSE, MAE, correlation, R² against JEPX actuals."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_metrics(
    prices_df: pd.DataFrame,
    simulated_col: str = "clearing_price_jpy_kwh",
    actual_col: str = "actual_system_price_jpy_kwh",
) -> dict | None:
    """Compute backtest accuracy metrics.

    Returns None if actual prices are not available.
    """
    if actual_col not in prices_df.columns:
        return None

    valid = prices_df[[simulated_col, actual_col]].dropna()
    if valid.empty:
        return None

    sim = valid[simulated_col].values
    actual = valid[actual_col].values

    errors = sim - actual
    rmse = float(np.sqrt(np.mean(errors ** 2)))
    mae = float(np.mean(np.abs(errors)))
    bias = float(np.mean(errors))
    corr = float(np.corrcoef(sim, actual)[0, 1])
    r2 = corr ** 2

    # Percentage metrics
    mape = float(np.mean(np.abs(errors / np.where(actual == 0, np.nan, actual))) * 100)

    return {
        "n_observations": len(valid),
        "rmse_jpy_kwh": rmse,
        "mae_jpy_kwh": mae,
        "bias_jpy_kwh": bias,
        "correlation": corr,
        "r_squared": r2,
        "mape_pct": mape,
        "sim_mean_jpy_kwh": float(sim.mean()),
        "actual_mean_jpy_kwh": float(actual.mean()),
        "sim_std_jpy_kwh": float(sim.std()),
        "actual_std_jpy_kwh": float(actual.std()),
    }
