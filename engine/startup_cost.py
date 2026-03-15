"""Startup cost calculation for thermal generators.

Startup costs depend on how long a unit has been offline:
- Hot start:  offline < 2 hours  (boiler still warm)
- Warm start: offline 2–8 hours
- Cold start: offline > 8 hours  (full restart)

This matters most for LNG and coal units that cycle on/off during duck curve
conditions (solar noon surplus).  The LP/UC solver uses these costs as part of
the objective function to decide whether it's cheaper to keep a unit running at
minimum stable generation or to shut down and pay restart costs later.
"""

from __future__ import annotations

HOT_THRESHOLD_HOURS = 2
WARM_THRESHOLD_HOURS = 8


def classify_start_type(hours_offline: float) -> str:
    """Classify startup type based on hours offline.

    Returns one of 'hot', 'warm', or 'cold'.
    """
    if hours_offline < HOT_THRESHOLD_HOURS:
        return "hot"
    elif hours_offline < WARM_THRESHOLD_HOURS:
        return "warm"
    else:
        return "cold"


def startup_cost_per_mw(
    hours_offline: float,
    hot_jpy_per_mw: float,
    warm_jpy_per_mw: float,
    cold_jpy_per_mw: float,
) -> float:
    """Return the per-MW startup cost given offline duration."""
    start_type = classify_start_type(hours_offline)
    if start_type == "hot":
        return float(hot_jpy_per_mw)
    elif start_type == "warm":
        return float(warm_jpy_per_mw)
    else:
        return float(cold_jpy_per_mw)


def compute_startup_cost(
    hours_offline: float,
    installed_capacity_mw: float,
    hot_jpy_per_mw: float,
    warm_jpy_per_mw: float,
    cold_jpy_per_mw: float,
) -> float:
    """Compute total startup cost for a fleet.

    Parameters
    ----------
    hours_offline : float
        Number of hours the fleet has been offline.
    installed_capacity_mw : float
        Total installed capacity of the fleet (MW).
    hot_jpy_per_mw, warm_jpy_per_mw, cold_jpy_per_mw : float
        Startup cost per MW for each start type (JPY/MW).

    Returns
    -------
    float
        Total startup cost in JPY.
    """
    per_mw = startup_cost_per_mw(
        hours_offline, hot_jpy_per_mw, warm_jpy_per_mw, cold_jpy_per_mw
    )
    return per_mw * float(installed_capacity_mw)
