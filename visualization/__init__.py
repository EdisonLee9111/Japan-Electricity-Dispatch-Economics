"""Visualization module for Japan Electricity Dispatch Economics.

Provides 7 chart types covering merit order, duck curve, seasonal patterns,
dispatch stacks, price duration, scenario comparison, and backtesting.
"""

from .style import apply_style, fuel_color, fuel_label, FUEL_COLORS, FUEL_STACK_ORDER
from .merit_order_chart import plot_merit_order
from .duck_curve import plot_duck_curve
from .seasonal_heatmap import plot_seasonal_heatmap, plot_marginal_fuel_heatmap
from .dispatch_stack import plot_dispatch_stack
from .price_duration import plot_price_duration
from .scenario_comparison import plot_scenario_comparison
from .backtest_chart import plot_backtest

__all__ = [
    "apply_style",
    "fuel_color",
    "fuel_label",
    "FUEL_COLORS",
    "FUEL_STACK_ORDER",
    "plot_merit_order",
    "plot_duck_curve",
    "plot_seasonal_heatmap",
    "plot_marginal_fuel_heatmap",
    "plot_dispatch_stack",
    "plot_price_duration",
    "plot_scenario_comparison",
    "plot_backtest",
]
