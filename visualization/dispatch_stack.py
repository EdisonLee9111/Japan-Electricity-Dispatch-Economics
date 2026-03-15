"""Chart 4 — Dispatch stack (representative days).

Stacked area chart showing hourly generation by fuel type for 4 representative
days: winter peak, summer peak, spring solar-rich, autumn solar-rich.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .style import apply_style, fuel_color, fuel_label, FUEL_STACK_ORDER


# (label, month, pick_strategy)
REPRESENTATIVE_DAYS = [
    ("Winter Peak (Jan)", 1, "max_demand"),
    ("Spring Solar-Rich (Apr)", 4, "median_demand"),
    ("Summer Peak (Aug)", 8, "max_demand"),
    ("Autumn Solar-Rich (Oct)", 10, "median_demand"),
]


def _pick_day(prices_df: pd.DataFrame, month: int, strategy: str) -> str:
    """Pick a representative date within a month."""
    df = prices_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df["month"] = df["timestamp"].dt.month

    month_df = df[df["month"] == month]
    if month_df.empty:
        # Try adjacent month
        month_df = df[df["month"] == ((month % 12) + 1)]
    if month_df.empty:
        return str(df["date"].iloc[0])

    daily = month_df.groupby("date")["demand_mw"].mean()

    if strategy == "max_demand":
        return str(daily.idxmax())
    else:
        median = daily.median()
        return str((daily - median).abs().idxmin())


def plot_dispatch_stack(
    prices_df: pd.DataFrame,
    dispatch_df: pd.DataFrame,
    *,
    title: str = "Dispatch Stack — Representative Days",
    output_path: Path | None = None,
) -> plt.Figure:
    """Draw 2×2 panel of stacked dispatch for representative days."""
    apply_style()

    pdf = prices_df.copy()
    pdf["timestamp"] = pd.to_datetime(pdf["timestamp"])
    ddf = dispatch_df.copy()
    ddf["timestamp"] = pd.to_datetime(ddf["timestamp"])

    fig, axes = plt.subplots(2, 2, figsize=(16, 10), sharex=True)
    axes_flat = axes.flatten()

    for idx, (label, month, strategy) in enumerate(REPRESENTATIVE_DAYS):
        ax = axes_flat[idx]
        target_date = _pick_day(pdf, month, strategy)

        day_dispatch = ddf[ddf["timestamp"].dt.date.astype(str) == target_date].copy()
        day_prices = pdf[pdf["timestamp"].dt.date.astype(str) == target_date].copy()

        if day_dispatch.empty:
            ax.set_title(f"{label}\n(no data)")
            continue

        day_dispatch["hour"] = (
            day_dispatch["timestamp"].dt.hour
            + day_dispatch["timestamp"].dt.minute / 60.0
        )

        pivot = day_dispatch.pivot_table(
            index="hour", columns="fuel_type", values="dispatched_mw", aggfunc="sum"
        ).fillna(0) / 1000.0

        fuels_present = [f for f in FUEL_STACK_ORDER if f in pivot.columns]
        bottom = np.zeros(len(pivot))
        for fuel in fuels_present:
            vals = pivot[fuel].values
            ax.fill_between(
                pivot.index, bottom, bottom + vals,
                color=fuel_color(fuel), alpha=0.75, linewidth=0,
                label=fuel_label(fuel),
            )
            bottom += vals

        # Demand overlay
        if not day_prices.empty:
            day_prices["hour"] = (
                day_prices["timestamp"].dt.hour
                + day_prices["timestamp"].dt.minute / 60.0
            )
            ax.plot(
                day_prices["hour"],
                day_prices["demand_mw"] / 1000.0,
                color="black", linewidth=2, linestyle="--", label="Demand",
            )

        ax.set_title(f"{label}\n({target_date})")
        ax.set_ylabel("GW")
        ax.set_xlim(0, 24)
        ax.set_ylim(0)

    axes_flat[2].set_xlabel("Hour of Day")
    axes_flat[3].set_xlabel("Hour of Day")

    # Shared legend
    handles, labels_list = axes_flat[0].get_legend_handles_labels()
    by_label = dict(zip(labels_list, handles))
    fig.legend(
        by_label.values(), by_label.keys(),
        loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.02),
    )
    fig.suptitle(title, fontsize=14, fontweight="bold", y=1.01)
    fig.tight_layout()

    if output_path:
        fig.savefig(output_path)
        plt.close(fig)
    return fig
