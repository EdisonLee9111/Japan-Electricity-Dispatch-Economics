"""Chart 3 — Seasonal dispatch heatmap.

24 hours (x-axis) × 12 months (y-axis), coloured by average clearing price.
Visually shows how LNG shifts from baseload in winter to peaker in spring.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from .style import apply_style


def plot_seasonal_heatmap(
    prices_df: pd.DataFrame,
    *,
    value_col: str = "clearing_price_jpy_kwh",
    title: str = "Average Clearing Price by Hour and Month (JPY/kWh)",
    output_path: Path | None = None,
) -> plt.Figure:
    """Draw a 24 × 12 heatmap of average clearing prices."""
    apply_style()

    df = prices_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["hour"] = df["timestamp"].dt.hour
    df["month"] = df["timestamp"].dt.month

    pivot = df.pivot_table(index="month", columns="hour", values=value_col, aggfunc="mean")

    month_labels = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    # Only use labels for months present in data
    present_months = sorted(pivot.index)
    y_labels = [month_labels[m - 1] for m in present_months]

    fig, ax = plt.subplots(figsize=(14, 6))
    sns.heatmap(
        pivot,
        ax=ax,
        cmap="YlOrRd",
        linewidths=0.3,
        linecolor="white",
        cbar_kws={"label": "JPY/kWh"},
        yticklabels=y_labels,
        fmt=".1f",
        annot=True,
        annot_kws={"size": 7},
    )
    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("Month")
    ax.set_title(title)

    if output_path:
        fig.savefig(output_path)
        plt.close(fig)
    return fig


def plot_marginal_fuel_heatmap(
    prices_df: pd.DataFrame,
    *,
    title: str = "Dominant Marginal Fuel by Hour and Month",
    output_path: Path | None = None,
) -> plt.Figure:
    """Draw a 24 × 12 heatmap showing the most frequent marginal fuel."""
    apply_style()
    from .style import fuel_color

    df = prices_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["hour"] = df["timestamp"].dt.hour
    df["month"] = df["timestamp"].dt.month

    # Most common marginal fuel in each (month, hour) bin
    mode_df = (
        df.groupby(["month", "hour"])["marginal_fuel"]
        .agg(lambda x: x.value_counts().index[0])
        .unstack(level="hour")
    )

    # Encode fuels as integers for colour mapping
    all_fuels = sorted(mode_df.values.ravel().tolist())
    unique_fuels = sorted(set(all_fuels))
    fuel_to_int = {f: i for i, f in enumerate(unique_fuels)}
    numeric = mode_df.map(lambda x: fuel_to_int.get(x, -1))

    from matplotlib.colors import ListedColormap
    colors = [fuel_color(f) for f in unique_fuels]
    cmap = ListedColormap(colors)

    month_labels = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    present_months = sorted(numeric.index)
    y_labels = [month_labels[m - 1] for m in present_months]

    fig, ax = plt.subplots(figsize=(14, 6))
    im = ax.imshow(numeric.values, aspect="auto", cmap=cmap, interpolation="nearest")

    ax.set_xticks(range(24))
    ax.set_xticklabels(range(24))
    ax.set_yticks(range(len(y_labels)))
    ax.set_yticklabels(y_labels)
    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("Month")
    ax.set_title(title)

    # Legend
    from matplotlib.patches import Patch
    from .style import fuel_label
    legend_elements = [Patch(facecolor=fuel_color(f), label=fuel_label(f)) for f in unique_fuels]
    ax.legend(handles=legend_elements, loc="upper right", ncol=2, fontsize=7)

    if output_path:
        fig.savefig(output_path)
        plt.close(fig)
    return fig
