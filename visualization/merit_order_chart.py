"""Chart 1 — Merit order curve.

X = cumulative capacity (GW), Y = marginal cost (JPY/kWh).
Colour-coded by fuel type.  This is the signature chart of production cost
modelling and should be generated for a single representative timestamp.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .style import apply_style, fuel_color, fuel_label


def plot_merit_order(
    fleet_df: pd.DataFrame,
    fuel_prices_row: dict | pd.Series | None = None,
    *,
    title: str = "Japan Electricity Merit Order Curve",
    output_path: Path | None = None,
) -> plt.Figure:
    """Draw a step-function merit-order supply curve.

    Parameters
    ----------
    fleet_df : DataFrame
        Fleet table with columns: fuel_type, installed_capacity_mw,
        marginal_cost_jpy_mwh.  If marginal_cost_jpy_mwh is missing,
        supply ``fuel_prices_row`` so costs can be computed on the fly.
    fuel_prices_row : dict, optional
        A single row of fuel prices used to compute marginal costs when
        they are not already present in *fleet_df*.
    """
    apply_style()

    df = fleet_df.copy()

    # Compute marginal costs on the fly if needed
    if "marginal_cost_jpy_mwh" not in df.columns and fuel_prices_row is not None:
        from engine.merit_order import build_merit_order
        df = build_merit_order(df, fuel_prices_row)

    # Exclude renewables for the thermal merit-order curve visual
    # but include them as a hatched block at the left to show must-take
    renewable_mask = df["fuel_type"].isin({"solar", "wind"})
    renewables = df[renewable_mask].copy()
    thermals = df[~renewable_mask].sort_values("marginal_cost_jpy_mwh").copy()

    fig, ax = plt.subplots(figsize=(14, 6))

    cumulative_gw = 0.0

    # Draw renewable block (zero marginal cost, hatched)
    for _, row in renewables.iterrows():
        width = row["installed_capacity_mw"] / 1000.0
        ax.bar(
            cumulative_gw + width / 2,
            row["marginal_cost_jpy_mwh"] / 1000.0 + 0.5,  # small visible height
            width=width,
            color=fuel_color(row["fuel_type"]),
            alpha=0.5,
            edgecolor="black",
            linewidth=0.5,
            label=fuel_label(row["fuel_type"]),
            hatch="//",
        )
        cumulative_gw += width

    # Draw thermal/dispatchable blocks
    for _, row in thermals.iterrows():
        width = row["installed_capacity_mw"] / 1000.0
        cost_kwh = row["marginal_cost_jpy_mwh"] / 1000.0
        ax.bar(
            cumulative_gw + width / 2,
            cost_kwh,
            width=width,
            color=fuel_color(row["fuel_type"]),
            edgecolor="black",
            linewidth=0.5,
            label=fuel_label(row["fuel_type"]),
        )
        cumulative_gw += width

    ax.set_xlabel("Cumulative Capacity (GW)")
    ax.set_ylabel("Marginal Cost (JPY/kWh)")
    ax.set_title(title)

    # De-duplicate legend entries
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), loc="upper left")

    ax.set_xlim(0, cumulative_gw * 1.02)
    ax.set_ylim(0)

    if output_path:
        fig.savefig(output_path)
        plt.close(fig)
    return fig
