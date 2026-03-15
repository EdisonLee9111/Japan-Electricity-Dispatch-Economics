"""Scenario engine for Japan Electricity Dispatch Economics."""

from .config import ScenarioConfig, ALL_SCENARIOS, BASE_CASE, NUCLEAR_RESTART, LNG_PRICE_SHOCK, SOLAR_DOUBLING, get_scenario
from .runner import apply_scenario, run_scenario, run_all_scenarios, write_scenario_results
from .comparator import compare_all, print_comparison_report, write_comparison
