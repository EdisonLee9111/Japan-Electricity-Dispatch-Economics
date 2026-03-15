"""Chart 7 — Backtest: simulated vs actual JEPX price comparison.

Time series comparison with correlation coefficient and RMSE annotation.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .style import apply_style


def plot_backtest(
    prices_df: pd.DataFrame,
    *,
    simulated_col: str = "clearing_price_jpy_kwh",
    actual_col: str = "actual_system_price_jpy_kwh",
    title: str = "Backtest — Simulated vs Actual JEPX System Price",
    output_path: Path | None = None,
) -> plt.Figure | None:
    """Draw simulated vs actual JEPX price comparison.

    Returns None if actual prices are not available.
    """
    apply_style()

    df = prices_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    if actual_col not in df.columns:
        return None

    valid = df[[simulated_col, actual_col]].dropna()
    if valid.empty:
        return None

    df_valid = df.loc[valid.index].copy()

    # Compute metrics
    sim = df_valid[simulated_col].values
    actual = df_valid[actual_col].values
    rmse = np.sqrt(np.mean((sim - actual) ** 2))
    mae = np.mean(np.abs(sim - actual))
    corr = np.corrcoef(sim, actual)[0, 1]
    r2 = corr ** 2

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))

    # Panel 1: Time series (daily average for readability)
    ax = axes[0, 0]
    daily = df_valid.set_index("timestamp")[[simulated_col, actual_col]].resample("D").mean()
    ax.plot(daily.index, daily[actual_col], color="#2C3E50", linewidth=1, alpha=0.8, label="Actual JEPX")
    ax.plot(daily.index, daily[simulated_col], color="#E67E22", linewidth=1, alpha=0.8, label="Simulated")
    ax.set_ylabel("JPY/kWh")
    ax.set_title("Daily Average Price")
    ax.legend(fontsize=8)

    # Panel 2: Scatter plot
    ax = axes[0, 1]
    ax.scatter(actual, sim, alpha=0.05, s=3, color="#2C3E50")
    max_val = max(actual.max(), sim.max()) * 1.05
    ax.plot([0, max_val], [0, max_val], "r--", linewidth=1, label="Perfect forecast")
    ax.set_xlabel("Actual JEPX (JPY/kWh)")
    ax.set_ylabel("Simulated (JPY/kWh)")
    ax.set_title("Scatter — Simulated vs Actual")
    ax.set_xlim(0, max_val)
    ax.set_ylim(0, max_val)
    ax.set_aspect("equal")
    ax.legend(fontsize=8)

    # Metrics annotation box
    metrics_text = (
        f"RMSE: {rmse:.2f} JPY/kWh\n"
        f"MAE:  {mae:.2f} JPY/kWh\n"
        f"R²:   {r2:.3f}\n"
        f"Corr: {corr:.3f}\n"
        f"N:    {len(valid):,}"
    )
    ax.text(
        0.05, 0.95, metrics_text, transform=ax.transAxes,
        fontsize=9, verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="wheat", alpha=0.8),
    )

    # Panel 3: Error distribution
    ax = axes[1, 0]
    errors = sim - actual
    ax.hist(errors, bins=80, color="#3498DB", edgecolor="white", linewidth=0.3, alpha=0.8)
    ax.axvline(0, color="red", linewidth=1.5, linestyle="--")
    ax.set_xlabel("Error (Simulated − Actual) JPY/kWh")
    ax.set_ylabel("Frequency")
    ax.set_title(f"Error Distribution (bias: {errors.mean():+.2f} JPY/kWh)")

    # Panel 4: Error by hour of day
    ax = axes[1, 1]
    df_valid["error"] = df_valid[simulated_col] - df_valid[actual_col]
    df_valid["hour"] = df_valid["timestamp"].dt.hour
    hourly_error = df_valid.groupby("hour")["error"].agg(["mean", "std"])
    ax.bar(hourly_error.index, hourly_error["mean"], color="#E74C3C", alpha=0.7,
           edgecolor="white", linewidth=0.3)
    ax.errorbar(hourly_error.index, hourly_error["mean"], yerr=hourly_error["std"],
                fmt="none", color="black", capsize=2, linewidth=0.8)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("Mean Error (JPY/kWh)")
    ax.set_title("Forecast Error by Hour of Day")

    fig.suptitle(title, fontsize=14, fontweight="bold", y=1.01)
    fig.tight_layout()

    if output_path:
        fig.savefig(output_path)
        plt.close(fig)
    return fig
