"""Backtest module for Japan Electricity Dispatch Economics.

Compares simulated clearing prices against actual JEPX spot prices,
computing accuracy metrics and structured deviation analysis.
"""

from .metrics import compute_metrics
from .price_comparison import run_backtest
from .deviation_analysis import analyse_deviations, print_deviation_report, write_deviation_report

__all__ = [
    "compute_metrics",
    "run_backtest",
    "analyse_deviations",
    "print_deviation_report",
    "write_deviation_report",
]
