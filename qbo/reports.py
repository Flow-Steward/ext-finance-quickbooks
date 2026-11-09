"""Bounded financial report options; provider totals are never recalculated."""

from __future__ import annotations

from datetime import date
from typing import Any

from qbo.validation import integer, require, text

REPORT_FIELDS = frozenset(
    {
        "start_date",
        "end_date",
        "report_date",
        "date_macro",
        "accounting_method",
        "summarize_column_by",
        "customer",
        "vendor",
        "item",
        "department",
        "class",
        "account",
        "source_account",
        "sort_by",
        "sort_order",
        "columns",
        "aging_method",
        "days_per_aging_period",
        "num_periods",
        "account_type",
        "account_status",
        "arpaid",
        "appaid",
    }
)
SUMMARY_VALUES = frozenset(
    {
        "Total",
        "Month",
        "Week",
        "Days",
        "Quarters",
        "Year",
        "Customers",
        "Vendors",
        "Employees",
        "Departments",
        "Classes",
        "ProductsAndServices",
    }
)


def report_options(entity: str, raw: Any) -> dict[str, str]:
    require(isinstance(raw, dict) and set(raw) <= REPORT_FIELDS, "Unknown report option.")
    options: dict[str, str] = {}
    for key, value in raw.items():
        if key in ("days_per_aging_period", "num_periods"):
            options[key] = str(integer(value, 1, 365 if key == "days_per_aging_period" else 100))
        else:
            options[key] = text(value, 2048)
        if key.endswith("_date"):
            require(
                len(options[key]) == 10
                and date.fromisoformat(options[key]).isoformat() == options[key],
                "Invalid report date.",
            )
    if "start_date" in options and "end_date" in options:
        require(options["start_date"] <= options["end_date"], "Report start is after its end.")
    if "accounting_method" in options:
        require(options["accounting_method"] in ("Cash", "Accrual"), "Unknown accounting method.")
    if "aging_method" in options:
        require(options["aging_method"] in ("Current", "Report_Date"), "Unknown aging method.")
    if "summarize_column_by" in options:
        require(options["summarize_column_by"] in SUMMARY_VALUES, "Unknown report summarization.")
    if entity == "BalanceSheet" and "end_date" in options and "start_date" not in options:
        options["start_date"] = options["end_date"][:4] + "-01-01"
    return options
