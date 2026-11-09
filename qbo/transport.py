"""One bounded, DNS-pinned HTTPS request to a fixed Intuit API origin."""

from __future__ import annotations

import ipaddress
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

from flowsteward_extension_sdk import open_pinned_url, resolve_pinned_ips

from qbo.commands import Plan
from qbo.validation import PDF_LIMIT, RESULT_LIMIT, Failure, require

ORIGINS = {
    "sandbox": "sandbox-quickbooks.api.intuit.com",
    "production": "quickbooks.api.intuit.com",
}
ERROR_LIMIT = 32 * 1024
READ_CHUNK = 64 * 1024


def fault_failure(value: Any, *, dispatched: bool = False) -> Failure | None:
    if not isinstance(value, dict) or "Fault" not in value:
        return None
    fault = value["Fault"]
    errors = fault.get("Error", []) if isinstance(fault, dict) else []
    codes = (
        {str(row.get("code", "")) for row in errors if isinstance(row, dict)}
        if isinstance(errors, list)
        else set()
    )
    code = (
        "conflict"
        if codes & {"5010", "6240"}
        else "authentication_failed"
        if "3200" in codes
        else "not_found"
        if "610" in codes
        else "provider_validation"
    )
    unknown = dispatched and isinstance(fault, dict) and fault.get("type") == "SystemFault"
    return Failure(
        code,
        "QuickBooks rejected the request. Review entity state, version and API field requirements.",
        applied_unknown=unknown,
    )


class Transport:
    """HTTP adapter. A connection fixes both the environment and company path."""

    def __init__(self, config: dict[str, Any], token: str, request_id: str = "") -> None:
        self.config = config
        self.token = token
        self.request_id = request_id
        self.host = ORIGINS[config["environment"]]
        self.deadline = time.monotonic() + config["request_timeout_seconds"]
        self.dispatched = False

    def request(
        self, plan: Plan, *, body: bytes | None = None, content_type: str = "application/json"
    ) -> Any:
        query = {"minorversion": str(self.config["minor_version"]), **plan.query}
        if plan.method == "POST":
            require(
                bool(self.request_id),
                "A request ID is required for accounting writes.",
                "effect_claim_required",
            )
            query["requestid"] = self.request_id
        require(
            plan.path.startswith("/") and not plan.path.startswith("//") and "?" not in plan.path,
            "Invalid internal provider route.",
        )
        url = f"https://{self.host}/v3/company/{self.config['realm_id']}{plan.path}?{urlencode(query)}"
        data = (
            body
            if body is not None
            else (
                json.dumps(plan.body, ensure_ascii=False, allow_nan=False).encode()
                if plan.body is not None
                else None
            )
        )
        request = Request(
            url,
            data=data,
            method=plan.method,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/pdf" if plan.kind == "pdf" else "application/json",
                "Content-Type": content_type,
            },
        )
        try:
            ips = tuple(resolve_pinned_ips(self.host, port=443, purpose="QuickBooks API"))
            require(
                ips and all(ipaddress.ip_address(ip).is_global for ip in ips),
                "QuickBooks DNS resolved to a forbidden address.",
                "network_blocked",
            )
        except (OSError, ValueError):
            raise Failure(
                "network_blocked",
                "QuickBooks DNS resolution failed or returned a forbidden address.",
            ) from None
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, "Operation deadline exceeded.", "timeout")
        self.dispatched = plan.method == "POST"
        try:
            with open_pinned_url(
                request, timeout_seconds=remaining, purpose="QuickBooks API", pinned_ips=ips
            ) as response:
                require(
                    response.status == 200,
                    "Unexpected QuickBooks response status.",
                    "invalid_provider_response",
                )
                raw = self._read(response, PDF_LIMIT if plan.kind == "pdf" else RESULT_LIMIT)
        except HTTPError as exc:
            raise self._http_failure(exc) from None
        except (TimeoutError, OSError, URLError):
            raise Failure(
                "provider_unavailable",
                "QuickBooks request failed. No automatic retry was performed.",
                applied_unknown=self.dispatched,
            ) from None
        if plan.kind == "pdf":
            require(
                raw.startswith(b"%PDF-"),
                "QuickBooks did not return a PDF.",
                "invalid_provider_response",
            )
            return raw
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError, RecursionError):
            raise Failure(
                "invalid_provider_response",
                "QuickBooks returned invalid JSON.",
                applied_unknown=self.dispatched,
            ) from None
        require(
            isinstance(value, dict),
            "QuickBooks returned an invalid response envelope.",
            "invalid_provider_response",
        )
        failure = fault_failure(value, dispatched=self.dispatched)
        if failure:
            raise failure
        return value

    def _read(self, response: Any, maximum: int) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            if time.monotonic() >= self.deadline:
                raise Failure(
                    "timeout",
                    "QuickBooks response deadline exceeded.",
                    applied_unknown=self.dispatched,
                )
            chunk = response.read(min(READ_CHUNK, maximum + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                raise Failure(
                    "response_too_large",
                    "QuickBooks response exceeds the byte limit.",
                    applied_unknown=self.dispatched,
                )
            chunks.append(chunk)
        return b"".join(chunks)

    def _http_failure(self, exc: HTTPError) -> Failure:
        try:
            raw = exc.read(ERROR_LIMIT + 1)
            value = json.loads(raw) if len(raw) <= ERROR_LIMIT else {}
            fault = fault_failure(value, dispatched=self.dispatched)
        except (ValueError, OSError, RecursionError):
            fault = None
        finally:
            exc.close()
        if fault:
            return fault
        code = {
            400: "provider_validation",
            401: "authentication_failed",
            403: "authentication_failed",
            404: "not_found",
            409: "conflict",
            429: "rate_limited",
        }.get(exc.code, "provider_unavailable")
        return Failure(
            code,
            f"QuickBooks returned HTTP {exc.code}.",
            applied_unknown=self.dispatched and exc.code >= 500,
        )
