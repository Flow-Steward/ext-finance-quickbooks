"""Native REST request plans with explicit entity mutation semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qbo.catalog import INACTIVE_ENTITIES, OPERATIONS, VOID_ENTITIES
from qbo.queries import select_query
from qbo.reports import report_options
from qbo.validation import Failure, bounded_json, identifier, require, text


@dataclass(frozen=True)
class Plan:
    method: str
    path: str
    body: dict[str, Any] | None = None
    query: dict[str, str] = field(default_factory=dict)
    entity: str = ""
    kind: str = ""


def prepare(name: str, args: dict[str, Any], realm_id: str) -> Plan:
    spec = OPERATIONS.get(name)
    if spec is None:
        raise Failure("invalid_payload", "Unknown QuickBooks operation.")
    kind, entity = spec["kind"], spec["entity"]
    path = "/" + entity.lower()
    if kind == "report":
        return Plan(
            "GET",
            "/reports/" + entity,
            query=report_options(entity, args.get("options", {})),
            entity=entity,
            kind=kind,
        )
    if kind == "search":
        return Plan(
            "GET", "/query", query={"query": select_query(entity, args)}, entity=entity, kind=kind
        )
    if kind == "pdf":
        return Plan(
            "GET",
            "/invoice/" + identifier(args.get("entity_id")) + "/pdf",
            entity=entity,
            kind=kind,
        )
    if kind in ("get", "read"):
        if entity == "Preferences":
            return Plan("GET", path, entity=entity, kind=kind)
        eid = realm_id if entity == "CompanyInfo" else identifier(args.get("entity_id"))
        return Plan("GET", path + "/" + eid, entity=entity, kind=kind)
    if kind == "delete":
        return _delete(entity, path, args)
    data = args.get("data")
    if not isinstance(data, dict) or not data:
        raise Failure("invalid_payload", "data must be a nonempty native QBO object.")
    bounded_json(data)
    data = dict(data)
    if kind == "update":
        identifier(data.get("Id"))
        require(text(data.get("SyncToken"), 32).isdigit(), "SyncToken must be a version string.")
        data.setdefault("sparse", True)
        require(type(data["sparse"]) is bool, "sparse must be boolean.")
    elif kind == "create":
        # Caller-provided read-only identifiers are never accidentally interpreted as updates.
        require(
            "Id" not in data and "SyncToken" not in data, "Create cannot supply Id or SyncToken."
        )
    else:
        raise Failure("invalid_payload", "Unknown operation kind.")
    return Plan(
        "POST", path, data, {"operation": "update"} if kind == "update" else {}, entity, kind
    )


def _delete(entity: str, path: str, args: dict[str, Any]) -> Plan:
    eid = identifier(args.get("entity_id"))
    version = text(args.get("sync_token"), 32)
    require(version.isdigit(), "sync_token must be a version string.")
    mode = args.get("delete_mode", "delete")
    require(mode in ("delete", "void"), "Unknown deletion mode.")
    data: dict[str, Any] = {"Id": eid, "SyncToken": version}
    if entity in INACTIVE_ENTITIES:
        require(mode == "delete", "This entity supports inactivation, not voiding.")
        data.update(sparse=True, Active=False)
        query: dict[str, str] = {"operation": "update"}
    else:
        require(mode != "void" or entity in VOID_ENTITIES, "This entity does not support voiding.")
        query = {"operation": mode}
        if entity in {"Payment", "SalesReceipt"} and mode == "void":
            # Payment and SalesReceipt voiding use a sparse update, unlike the transaction void endpoint.
            data["sparse"] = True
            query = {"operation": "update", "include": "void"}
    return Plan("POST", path, data, query, entity, "delete")
