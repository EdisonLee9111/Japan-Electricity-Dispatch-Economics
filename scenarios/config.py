"""Scenario configuration for Japan Electricity Dispatch Economics.

Each scenario modifies base-case fleet and fuel-price parameters to answer
specific 'what-if' questions about Japan's electricity dispatch economics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class ScenarioConfig:
    """Parameterised scenario definition.

    Fleet modifications are expressed as absolute values (GW).
    Fuel-price and demand modifications are multipliers (1.0 = no change).
    """

    name: str
    description: str

    # Fleet capacity overrides (GW → converted to MW internally)
    nuclear_capacity_gw: float | None = None
    solar_capacity_gw: float | None = None
    wind_capacity_gw: float | None = None

    # Fuel-price multipliers (applied to time-series prices)
    lng_price_multiplier: float = 1.0
    coal_price_multiplier: float = 1.0
    oil_price_multiplier: float = 1.0

    # Demand multiplier
    demand_multiplier: float = 1.0

    def __post_init__(self) -> None:
        for attr in ("lng_price_multiplier", "coal_price_multiplier",
                     "oil_price_multiplier", "demand_multiplier"):
            if getattr(self, attr) <= 0:
                raise ValueError(f"{attr} must be positive, got {getattr(self, attr)}")


# ── Pre-built scenarios ──────────────────────────────────────────────────────

BASE_CASE = ScenarioConfig(
    name="base",
    description="Current fleet composition and fuel prices (FY2025 actuals).",
)

NUCLEAR_RESTART = ScenarioConfig(
    name="nuclear_restart",
    description=(
        "Aggressive nuclear restart: capacity from ~10 GW to 25 GW, "
        "reflecting restart of additional idled reactors. Expected: lower "
        "clearing prices, increased solar curtailment risk, reduced LNG utilisation."
    ),
    nuclear_capacity_gw=25.0,
)

LNG_PRICE_SHOCK = ScenarioConfig(
    name="lng_price_shock",
    description=(
        "LNG price × 1.5 simulating supply disruption or Asian premium spike. "
        "Expected: LNG units move up the merit order, coal becomes more competitive, "
        "clearing prices rise during LNG-marginal hours."
    ),
    lng_price_multiplier=1.5,
)

SOLAR_DOUBLING = ScenarioConfig(
    name="solar_doubling",
    description=(
        "Solar capacity from 80 GW to 160 GW (2030 trajectory). Expected: "
        "deeper duck curve, more hours of near-zero prices, increased cycling "
        "burden on thermal units."
    ),
    solar_capacity_gw=160.0,
)

# Canonical list used by the scenario runner
ALL_SCENARIOS: list[ScenarioConfig] = [
    BASE_CASE,
    NUCLEAR_RESTART,
    LNG_PRICE_SHOCK,
    SOLAR_DOUBLING,
]


def get_scenario(name: str) -> ScenarioConfig:
    """Look up a scenario by name."""
    for s in ALL_SCENARIOS:
        if s.name == name:
            return s
    raise KeyError(f"Unknown scenario '{name}'. Available: {[s.name for s in ALL_SCENARIOS]}")
