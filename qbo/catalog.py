"""Pinned operation capabilities, shared by the planner and runtime."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CATALOG: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parents[1] / "contracts/catalog.yaml").read_text()
)
OPERATIONS: dict[str, dict[str, str]] = CATALOG["operations"]
WRITE_KINDS = frozenset({"create", "update", "delete"})
INACTIVE_ENTITIES = frozenset({"Customer", "Vendor", "Employee", "Item"})
VOID_ENTITIES = frozenset({"Invoice", "Payment", "SalesReceipt"})
