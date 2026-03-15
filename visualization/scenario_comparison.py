"""Chart 6 — Scenario comparison dashboard.

Multi-panel bar charts comparing key metrics (average price, generation mix,
capacity factors) across all scenarios.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .style import apply_style, fuel_color, fuel_label, FUEL_STACK_ORDER


def plot_scenario_comparison(
    summary_table: pd.DataFrame,
    *,
    title: str = "Scenario Comparison Dashboard",
    output_path: Path | None = None,
) -> plt.Figure:
    """Draw a multi-panel comparison from the scenario summary table.

    Parameters
    ----------
    summary_table : DataFrame
        Output from comparator.compare_all(), indexed by scenario name.
        Expected columns include avg_price_jpy_kwh, gen_*_twh, cf_*.
    """
    apply_style()

    scenarios = summary_table.index.tolist()
    n_sc = len(scenarios)

    scenario_colors = {
        "base": "#2C3E50",
        "nuclear_restart": "#7B2D8E",
        "lng_price_shock": "#E67E22",
        "solar_doubling": "#F1C40F",
    }
    sc_colors = [scenario_colors.get(s, f"C{i}") for i, s in enumerate(scenarios)]

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))

    # Panel 1: Average price
    ax = axes[0, 0]
    prices = summary_table["avg_price_jpy_kwh"].values
    bars = ax.bar(range(n_sc), prices, color=sc_colors, edgecolor="black", linewidth=0.5)
    ax.set_xticks(range(n_sc))
    ax.set_xticklabels(scenarios, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("JPY/kWh")
    ax.set_title("Average Clearing Price")
    for bar, val in zip(bars, prices):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                f"{val:.2f}", ha="center", va="bottom", fontsize=8)

    # Panel 2: Generation mix (stacked bar)
    ax = axes[0, 1]
    gen_cols = [c for c in summary_table.columns if c.startswith("gen_") and c.endswith("_twh")]
    fuels_ordered = [f for f in FUEL_STACK_ORDER if f"gen_{f}_twh" in gen_cols]

    x = np.arange(n_sc)
    width = 0.6
    bottom = np.zeros(n_sc)
    for fuel in fuels_ordered:
        col = f"gen_{fuel}_twh"
        vals = summary_table[col].values
        ax.bar(x, vals, width, bottom=bottom, color=fuel_color(fuel),
               label=fuel_label(fuel), edgecolor="white", linewidth=0.3)
        bottom += vals

    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("TWh")
    ax.set_title("Generation Mix")
    ax.legend(loc="upper right", fontsize=7, ncol=2)

    # Panel 3: Capacity factors (grouped bar)
    ax = axes[1, 0]
    cf_cols = [c for c in summary_table.columns if c.startswith("cf_")]
    cf_fuels = [c.replace("cf_", "") for c in cf_cols]
    cf_fuels_ordered = [f for f in FUEL_STACK_ORDER if f in cf_fuels]

    n_fuels = len(cf_fuels_ordered)
    bar_width = 0.8 / n_sc
    for i, sc in enumerate(scenarios):
        vals = [summary_table.loc[sc, f"cf_{f}"] * 100 for f in cf_fuels_ordered]
        positions = np.arange(n_fuels) + i * bar_width
        ax.bar(positions, vals, bar_width, color=sc_colors[i], label=sc,
               edgecolor="white", linewidth=0.3)

    ax.set_xticks(np.arange(n_fuels) + bar_width * (n_sc - 1) / 2)
    ax.set_xticklabels([fuel_label(f) for f in cf_fuels_ordered], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Capacity Factor (%)")
    ax.set_title("Capacity Factors by Fuel")
    ax.legend(fontsize=7)

    # Panel 4: Low-price hours + curtailment
    ax = axes[1, 1]
    x = np.arange(n_sc)
    low_hours = summary_table["low_price_hours"].values

    ax.bar(x - 0.15, low_hours, 0.3, color="#3498DB", label="Low-price hours (<5 ¥/kWh)")

    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Hours / Year")
    ax.set_title("Duck Curve Severity & Curtailment")
    ax.legend(loc="upper left", fontsize=7)

    # Curtailment on secondary axis
    if "curtailment_twh" in summary_table.columns:
        ax2 = ax.twinx()
        curtailment = summary_table["curtailment_twh"].values
        ax2.bar(x + 0.15, curtailment, 0.3, color="#E74C3C", alpha=0.7, label="Curtailment (TWh)")
        ax2.set_ylabel("TWh Curtailed")
        ax2.legend(loc="upper right", fontsize=7)

    fig.suptitle(title, fontsize=14, fontweight="bold", y=1.01)
    fig.tight_layout()

    if output_path:
        fig.savefig(output_path)
        plt.close(fig)
    return fig
