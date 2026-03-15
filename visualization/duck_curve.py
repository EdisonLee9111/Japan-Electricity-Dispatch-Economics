"""Chart 2 — Duck curve visualisation.

Plots net load (demand minus solar/wind) for representative days, showing
the "belly" during solar noon and the evening ramp.  Overlays actual
dispatch to illustrate which fuels fill the belly and handle the ramp.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .style import apply_style, fuel_color, fuel_label, FUEL_STACK_ORDER


def _pick_representative_day(prices_df: pd.DataFrame, month: int) -> str:
    """Pick a weekday in the given month closest to the median demand."""
    df = prices_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df["month"] = df["timestamp"].dt.month
    df["dow"] = df["timestamp"].dt.dayofweek

    month_df = df[(df["month"] == month) & (df["dow"] < 5)]
    if month_df.empty:
        month_df = df[df["month"] == month]

    daily_demand = month_df.groupby("date")["demand_mw"].mean()
    median_demand = daily_demand.median()
    best_day = (daily_demand - median_demand).abs().idxmin()
    return str(best_day)


def plot_duck_curve(
    prices_df: pd.DataFrame,
    dispatch_df: pd.DataFrame,
    *,
    spring_month: int = 4,
    title: str = "Duck Curve — Net Load vs Gross Demand",
    output_path: Path | None = None,
) -> plt.Figure:
    """Draw the duck curve for a representative spring day.

    Shows gross demand, net load (demand − renewables), and the stacked
    dispatch of thermal fuels that fill the net-load valley.
    """
    apply_style()

    pdf = prices_df.copy()
    pdf["timestamp"] = pd.to_datetime(pdf["timestamp"])
    target_date = _pick_representative_day(pdf, spring_month)

    day_prices = pdf[pdf["timestamp"].dt.date.astype(str) == target_date].copy()
    day_prices["hour"] = day_prices["timestamp"].dt.hour + day_prices["timestamp"].dt.minute / 60.0

    ddf = dispatch_df.copy()
    ddf["timestamp"] = pd.to_datetime(ddf["timestamp"])
    day_dispatch = ddf[ddf["timestamp"].dt.date.astype(str) == target_date].copy()
    day_dispatch["hour"] = day_dispatch["timestamp"].dt.hour + day_dispatch["timestamp"].dt.minute / 60.0

    fig, ax = plt.subplots(figsize=(14, 7))

    hours = day_prices["hour"].values
    demand = day_prices["demand_mw"].values / 1000.0  # GW
    renewable_mw = day_prices["renewable_dispatched_mw"].values
    net_load = (day_prices["demand_mw"].values - renewable_mw) / 1000.0

    # Stacked dispatch by fuel
    pivot = day_dispatch.pivot_table(
        index="hour", columns="fuel_type", values="dispatched_mw", aggfunc="sum"
    ).fillna(0) / 1000.0

    # Stack in canonical order
    fuels_present = [f for f in FUEL_STACK_ORDER if f in pivot.columns]
    bottom = np.zeros(len(pivot))
    for fuel in fuels_present:
        vals = pivot[fuel].values
        ax.fill_between(
            pivot.index, bottom, bottom + vals,
            color=fuel_color(fuel), alpha=0.65,
            label=fuel_label(fuel), linewidth=0,
        )
        bottom += vals

    # Demand and net load lines
    ax.plot(hours, demand, color="black", linewidth=2.5, label="Gross Demand")
    ax.plot(hours, net_load, color="red", linewidth=2.5, linestyle="--", label="Net Load (Demand − RE)")

    # Annotate the duck belly
    min_idx = np.argmin(net_load)
    ax.annotate(
        f"Duck belly\n{net_load[min_idx]:.0f} GW",
        xy=(hours[min_idx], net_load[min_idx]),
        xytext=(hours[min_idx] + 2, net_load[min_idx] - 8),
        arrowprops=dict(arrowstyle="->", color="red"),
        fontsize=9, color="red", fontweight="bold",
    )

    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("Power (GW)")
    ax.set_title(f"{title}\n({target_date}, Spring Weekday)")
    ax.set_xlim(0, 24)
    ax.set_ylim(0)
    ax.legend(loc="upper left", ncol=2)

    if output_path:
        fig.savefig(output_path)
        plt.close(fig)
    return fig
