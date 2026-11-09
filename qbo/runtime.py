"""Explicit company selection, host boundary and external-effect policy."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from flowsteward_extension_sdk import runtime_context_from_payload

from qbo.catalog import OPERATIONS, WRITE_KINDS
from qbo.commands import prepare
from qbo.documents import save_pdf, upload_attachment
from qbo.results import normalize
from qbo.transport import Transport
from qbo.validation import RESULT_LIMIT, Failure, bounded_json, connection_values, require, text


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    transport: Transport | None = None
    try:
        bounded_json(payload)
        context = runtime_context_from_payload(payload)
        require(
            context.account_id and context.project_id,
            "An account and project are required.",
            "invalid_connection",
        )
        require(payload.get("mode") == "action", "An action envelope is required.")
        raw_context = payload["runtime_context"]
        require(type(raw_context.get("test_mode", False)) is bool, "test_mode must be boolean.")
        action = payload.get("action")
        if not isinstance(action, dict):
            raise Failure("invalid_payload", "Invalid action.")
        name = text(action.get("action_id"), 128)
        require(
            isinstance(name, str) and (name in OPERATIONS or name == "verify_company"),
            "Unknown QuickBooks operation.",
        )
        args = action.get("input", {})
        target = action.get("target", {})
        require(
            isinstance(args, dict) and isinstance(target, dict), "Invalid action input or target."
        )
        connection = target.get("connection", {})
        require(
            isinstance(connection, dict)
            and connection.get("connection_type") == "quickbooks_company",
            "Select a QuickBooks company connection.",
            "invalid_connection",
        )
        if name != "verify_company":
            require(
                isinstance(args.get("connection_ref"), str)
                and bool(args["connection_ref"])
                and connection.get("connection_id") == args["connection_ref"],
                "Select the matching explicit company connection.",
                "invalid_connection",
            )
        config, token = connection_values(connection)
        operation = "get_company_info" if name == "verify_company" else name
        plan = prepare(operation, args, config["realm_id"])
        request_id = ""
        if plan.kind in WRITE_KINDS:
            require(
                not raw_context.get("test_mode", False),
                "Accounting writes are suppressed in Test Run.",
                "test_mode_suppressed",
            )
            require(
                config["allow_" + plan.kind],
                "This write category is disabled for the connection.",
                "write_disabled",
            )
            claim = (
                text(raw_context.get("external_effect_id"), 512)
                if raw_context.get("external_effect_id")
                else ""
            )
            require(
                bool(claim),
                "A durable host external-effect claim is required.",
                "effect_claim_required",
            )
            identity = [
                context.account_id,
                context.project_id,
                connection.get("connection_id"),
                config["environment"],
                config["realm_id"],
                name,
                claim,
            ]
            request_id = hashlib.sha256(
                json.dumps(identity, separators=(",", ":")).encode()
            ).hexdigest()[:48]
        transport = Transport(config, token, request_id)
        if name == "create_attachable" and args.get("artifact_handle"):
            value = upload_attachment(payload, args, plan, transport)
        else:
            value = transport.request(plan)
        if name == "verify_company":
            data = normalize(plan, value, args)["data"]
            display = text(data.get("CompanyName"), 200)
            result: dict[str, Any] = {
                "subject": config["environment"] + ":" + config["realm_id"],
                "verified_display_name": display,
                "safe_metadata": {
                    "realm_id": config["realm_id"],
                    "environment": config["environment"],
                },
                "health": "ok",
            }
        elif plan.kind == "pdf":
            result = save_pdf(payload, value)
        else:
            result = normalize(plan, value, args)
        result = _redact(result, token)
        bounded_json(result, RESULT_LIMIT)
        return {"ok": True, "result": result, "errors": []}
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError) as exc:
        unknown = transport is not None and transport.dispatched
        if isinstance(exc, Failure):
            code, message = exc.code, str(exc)
            # Explicit provider rejection establishes a known outcome. Post-send
            # parsing/artifact failures remain uncertain for accounting writes.
            if code in (
                "provider_validation",
                "conflict",
                "authentication_failed",
                "not_found",
                "rate_limited",
            ):
                unknown = exc.applied_unknown
            else:
                unknown = unknown or exc.applied_unknown
        else:
            code, message = "invalid_payload", "Invalid input or provider response."
        return {
            "ok": False,
            "result": {},
            "error_code": code,
            "error": message,
            "errors": [{"code": code, "message": message}],
            "retryable": False,
            "definitely_no_external_effect": not unknown,
            "external_effect_status": "timeout_unknown" if unknown else "not_applied",
        }


def _redact(value: Any, token: str) -> Any:
    if isinstance(value, str):
        return value.replace(token, "[redacted]")
    if isinstance(value, list):
        return [_redact(item, token) for item in value]
    if isinstance(value, dict):
        return {
            str(key).replace(token, "[redacted]"): _redact(item, token)
            for key, item in value.items()
        }
    return value
