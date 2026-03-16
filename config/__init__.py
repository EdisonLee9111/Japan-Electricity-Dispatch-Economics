"""Configuration loader for the Japan Electric Market project."""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache

import yaml

_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.yaml"


@lru_cache(maxsize=1)
def load_settings() -> dict:
    """Load project settings from config/settings.yaml (cached)."""
    with open(_SETTINGS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_dispatch_config() -> dict:
    """Return dispatch-related settings with sensible defaults."""
    settings = load_settings()
    dispatch = settings.get("dispatch", {})
    return {
        "renewable_fuels": set(dispatch.get("renewable_fuels", ["solar", "wind"])),
        "must_run_fuels": set(dispatch.get("must_run_fuels", ["nuclear"])),
        "shoulder_months": set(dispatch.get("shoulder_months", [4, 5, 10, 11])),
    }


def get_market_config() -> dict:
    """Return market price bounds from settings."""
    settings = load_settings()
    market = settings.get("market", {})
    return {
        "price_floor_jpy_mwh": float(market.get("price_floor_jpy_mwh", 100.0)),
        "price_cap_jpy_mwh": float(market.get("price_cap_jpy_mwh", 99_990.0)),
    }
