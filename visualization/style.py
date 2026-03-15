"""Shared colour palette and style constants for all charts.

Fuel-type colours follow the dev-plan specification and are consistent
across every chart produced by this project.
"""

from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt

# ── Fuel-type colour map ─────────────────────────────────────────────────────

FUEL_COLORS: dict[str, str] = {
    "nuclear": "#7B2D8E",       # purple
    "coal": "#4A4A4A",          # dark gray
    "lng_ccgt": "#E67E22",      # orange
    "lng_ocgt": "#F5B041",      # light orange
    "oil": "#8B4513",           # brown
    "hydro": "#2E86C1",         # blue
    "solar": "#F1C40F",         # gold/yellow
    "wind": "#48C9B0",          # teal
    "biomass": "#27AE60",       # green
}

# Canonical stacking order (bottom → top) for dispatch stack charts
FUEL_STACK_ORDER: list[str] = [
    "nuclear",
    "coal",
    "lng_ccgt",
    "lng_ocgt",
    "oil",
    "hydro",
    "biomass",
    "solar",
    "wind",
]

FUEL_LABELS: dict[str, str] = {
    "nuclear": "Nuclear",
    "coal": "Coal",
    "lng_ccgt": "LNG CCGT",
    "lng_ocgt": "LNG OCGT",
    "oil": "Oil",
    "hydro": "Hydro",
    "solar": "Solar PV",
    "wind": "Wind",
    "biomass": "Biomass",
}


def fuel_color(fuel: str) -> str:
    """Return colour hex for a fuel type, grey fallback for unknowns."""
    return FUEL_COLORS.get(fuel, "#CCCCCC")


def fuel_label(fuel: str) -> str:
    """Return display label for a fuel type."""
    return FUEL_LABELS.get(fuel, fuel.replace("_", " ").title())


def apply_style() -> None:
    """Apply a clean, publication-quality matplotlib style."""
    plt.style.use("seaborn-v0_8-whitegrid")
    mpl.rcParams.update({
        "figure.dpi": 150,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "font.size": 10,
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "legend.fontsize": 8,
        "figure.figsize": (12, 6),
    })
