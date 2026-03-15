"""Chart 5 — Price duration curve.

All hourly prices sorted descending.  Shows how many hours per year the
price exceeds various thresholds.  Supports overlaying base vs scenario.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .style import apply_style


def plot_price_duration(
    prices_dict: dict[str, pd.DataFrame],
    *,
    price_col: str = "clearing_price_jpy_kwh",
    title: str = "Price Duration Curve — Base vs Scenarios",
    output_path: Path | None = None,
) -> plt.Figure:
    """Draw overlaid price duration curves.

    Parameters
    ----------
    prices_dict : dict[str, DataFrame]
        Mapping of scenario name → prices DataFrame.
        The first entry is drawn with a thick line (assumed base case).
    """
    apply_style()

    scenario_colors = {
        "base": "#2C3E50",
        "nuclear_restart": "#7B2D8E",
        "lng_price_shock": "#E67E22",
        "solar_doubling": "#F1C40F",
    }

    fig, ax = plt.subplots(figsize=(12, 6))

    for i, (name, pdf) in enumerate(prices_dict.items()):
        prices = pdf[price_col].dropna().sort_values(ascending=False).values
        x = np.arange(1, len(prices) + 1)
        pct = x / len(prices) * 100

        color = scenario_colors.get(name, f"C{i}")
        lw = 2.5 if i == 0 else 1.5
        ls = "-" if i == 0 else "--"

        ax.plot(pct, prices, color=color, linewidth=lw, linestyle=ls, label=name)

    ax.set_xlabel("Percentage of Time (%)")
    ax.set_ylabel("Clearing Price (JPY/kWh)")
    ax.set_title(title)
    ax.legend()
    ax.set_xlim(0, 100)
    ax.set_ylim(0)

    # Reference lines
    ax.axhline(y=10, color="gray", linewidth=0.8, linestyle=":", alpha=0.6)
    ax.axhline(y=15, color="gray", linewidth=0.8, linestyle=":", alpha=0.6)
    ax.axhline(y=20, color="gray", linewidth=0.8, linestyle=":", alpha=0.6)
    for y in [10, 15, 20]:
        ax.text(101, y, f"{y}", fontsize=7, va="center", color="gray")

    if output_path:
        fig.savefig(output_path)
        plt.close(fig)
    return fig
