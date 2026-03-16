"""Clearing-price helpers for the Level 1 dispatch engine."""

from __future__ import annotations

try:
    from config import get_market_config
    _market_cfg = get_market_config()
except ImportError:
    _market_cfg = {"price_floor_jpy_mwh": 100.0, "price_cap_jpy_mwh": 99_990.0}

# JEPX minimum bid price: 0.10 JPY/kWh = 100 JPY/MWh
PRICE_FLOOR_JPY_MWH: float = _market_cfg["price_floor_jpy_mwh"]
# Historical JEPX cap: 99.99 JPY/kWh = 99,990 JPY/MWh
PRICE_CAP_JPY_MWH: float = _market_cfg["price_cap_jpy_mwh"]


def clamp_price(
    price_jpy_mwh: float,
    price_floor_jpy_mwh: float = PRICE_FLOOR_JPY_MWH,
    price_cap_jpy_mwh: float = PRICE_CAP_JPY_MWH,
) -> float:
    """Clamp a price into the allowed market band."""
    return max(
        float(price_floor_jpy_mwh),
        min(float(price_jpy_mwh), float(price_cap_jpy_mwh)),
    )


def determine_clearing_price(
    marginal_cost_jpy_mwh: float | None,
    *,
    oversupplied: bool = False,
    shortage: bool = False,
    price_floor_jpy_mwh: float = PRICE_FLOOR_JPY_MWH,
    price_cap_jpy_mwh: float = PRICE_CAP_JPY_MWH,
) -> float:
    """Determine the Level 1 clearing price.

    Rules
    -----
    - Oversupply with renewable curtailment -> price floor
    - Supply shortage / unserved energy    -> price cap
    - Otherwise                            -> marginal cost of the last dispatched fleet
    """
    if oversupplied:
        return float(price_floor_jpy_mwh)

    if shortage:
        return float(price_cap_jpy_mwh)

    if marginal_cost_jpy_mwh is None:
        return float(price_floor_jpy_mwh)

    return clamp_price(
        marginal_cost_jpy_mwh,
        price_floor_jpy_mwh=price_floor_jpy_mwh,
        price_cap_jpy_mwh=price_cap_jpy_mwh,
    )
