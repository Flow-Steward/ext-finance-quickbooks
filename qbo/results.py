"""Normalize native provider responses without flattening accounting structures."""

from __future__ import annotations

from typing import Any

from qbo.commands import Plan
from qbo.transport import fault_failure
from qbo.validation import Failure, require


def normalize(plan: Plan, value: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    if plan.kind == "report":
        require(
            isinstance(value.get("Header"), dict) and isinstance(value.get("Columns"), dict),
            "Invalid report response.",
            "invalid_provider_response",
        )
        return {"data": value}
    if plan.kind == "search":
        query = value.get("QueryResponse")
        if not isinstance(query, dict):
            raise Failure("invalid_provider_response", "Invalid query response.")
        rows = query.get(plan.entity, [])
        require(
            isinstance(rows, list) and all(isinstance(row, dict) for row in rows),
            "Invalid query rows.",
            "invalid_provider_response",
        )
        total = query.get("totalCount")
        require(
            total is None or (type(total) is int and total >= 0),
            "Invalid query count.",
            "invalid_provider_response",
        )
        start = args.get("start_position", 1)
        limit = args.get("max_results", 100)
        require(
            len(rows) <= limit, "QuickBooks returned too many rows.", "invalid_provider_response"
        )
        next_start = start + len(rows) if not args.get("count") and len(rows) == limit else None
        return {"data": rows, "next_start_position": next_start, "total_count": total}
    if plan.entity == "Attachable" and "AttachableResponse" in value:
        entries = value["AttachableResponse"]
        require(
            isinstance(entries, list) and len(entries) == 1,
            "Invalid attachment response.",
            "invalid_provider_response",
        )
        value = entries[0]
        failure = fault_failure(value, dispatched=plan.method == "POST")
        if failure:
            raise failure
    data = value.get(plan.entity)
    require(
        isinstance(data, dict),
        "QuickBooks response is missing the requested entity.",
        "invalid_provider_response",
    )
    return {"data": data}
