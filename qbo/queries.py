"""Construct QBO SELECT statements from bounded structured criteria."""

from __future__ import annotations

import re
from typing import Any

from qbo.catalog import OPERATIONS
from qbo.validation import Failure, integer, require, text

OPERATORS = frozenset({"=", "!=", "<", ">", "<=", ">=", "LIKE", "IN"})


def field_name(value: Any) -> str:
    value = text(value, 128)
    require(
        re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)?", value),
        "Invalid query field.",
    )
    return value


def literal(value: Any) -> str:
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) in (int, float):
        return str(value)
    value = text(value, 4096)
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def condition(row: dict[str, Any]) -> str:
    require(
        isinstance(row, dict) and set(row) <= {"field", "operator", "value"},
        "Invalid filter condition.",
    )
    field = field_name(row.get("field"))
    op = row.get("operator", "=")
    require(isinstance(op, str) and op in OPERATORS, "Unsupported filter operator.")
    value = row.get("value")
    if op == "IN":
        if not isinstance(value, list) or not 1 <= len(value) <= 100:
            raise Failure("invalid_payload", "IN requires 1–100 values.")
        rendered = "(" + ", ".join(literal(item) for item in value) + ")"
    else:
        rendered = literal(value)
    return f"{field} {op} {rendered}"


def select_query(entity: str, args: dict[str, Any]) -> str:
    require(
        entity in {spec["entity"] for spec in OPERATIONS.values() if spec["kind"] == "search"},
        "Unknown query entity.",
    )
    count = args.get("count", False)
    require(type(count) is bool, "count must be boolean.")
    # QBO has no bind parameters: entity is catalog-closed; fields and literals below are validated.
    statement = f"SELECT {'COUNT(*)' if count else '*'} FROM {entity}"  # nosec B608
    filters = args.get("filters", {})
    require(isinstance(filters, dict) and len(filters) <= 32, "filters must be a bounded object.")
    if "conditions" in filters:
        require(set(filters) == {"conditions"}, "Do not mix filter styles.")
        conditions = filters["conditions"]
        require(
            isinstance(conditions, list) and len(conditions) <= 32, "Too many filter conditions."
        )
        clauses = [condition(row) for row in conditions]
    else:
        clauses = [condition({"field": key, "value": value}) for key, value in filters.items()]
    if clauses:
        statement += " WHERE " + " AND ".join(clauses)
    if args.get("order_by") is not None:
        require(not count, "Count queries cannot be sorted.")
        parts = text(args["order_by"], 140).split()
        require(len(parts) in (1, 2), "Invalid sort order.")
        direction = parts[1] if len(parts) == 2 else "ASC"
        require(direction in ("ASC", "DESC"), "Sort direction must be ASC or DESC.")
        statement += f" ORDERBY {field_name(parts[0])} {direction}"
    start = integer(args.get("start_position", 1), 1, 1000000000)
    limit = integer(args.get("max_results", 100), 1, 1000)
    if not count:
        statement += f" STARTPOSITION {start} MAXRESULTS {limit}"
    return statement
