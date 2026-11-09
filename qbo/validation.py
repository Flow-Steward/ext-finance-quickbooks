"""Bounded JSON, identifiers and connection configuration validation."""

from __future__ import annotations

import json
import math
import re
from typing import Any

INPUT_LIMIT = 2 * 1024 * 1024
JSON_LIMIT = 2 * 1024 * 1024
RESULT_LIMIT = 4 * 1024 * 1024
FILE_LIMIT = 100 * 1024 * 1024
PDF_LIMIT = 20 * 1024 * 1024


class Failure(ValueError):
    """A safe public failure with an explicit external-effect outcome."""

    def __init__(self, code: str, message: str, *, applied_unknown: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.applied_unknown = applied_unknown


def require(condition: Any, message: str, code: str = "invalid_payload") -> None:
    if not condition:
        raise Failure(code, message)


def text(value: Any, maximum: int = 512) -> str:
    require(
        isinstance(value, str) and 0 < len(value) <= maximum,
        "A bounded nonempty string is required.",
    )
    require(
        all(ord(c) >= 32 and not 127 <= ord(c) <= 159 for c in value),
        "Control characters are forbidden.",
    )
    return str(value)


def identifier(value: Any) -> str:
    value = text(value, 128)
    require(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value), "Invalid entity identifier.")
    return value


def integer(value: Any, low: int, high: int) -> int:
    require(type(value) is int and low <= value <= high, "Integer outside its permitted range.")
    return int(value)


def bounded_json(value: Any, maximum: int = JSON_LIMIT) -> None:
    def visit(item: Any, depth: int) -> None:
        require(depth <= 24, "JSON nesting exceeds the limit.")
        if isinstance(item, dict):
            require(
                len(item) <= 2048 and all(isinstance(k, str) for k in item), "Invalid JSON object."
            )
            for child in item.values():
                visit(child, depth + 1)
        elif isinstance(item, list):
            require(len(item) <= 10000, "Too many array items.")
            for child in item:
                visit(child, depth + 1)
        elif type(item) is float:
            require(math.isfinite(item), "JSON numbers must be finite.")
        else:
            require(item is None or type(item) in (str, bool, int), "Invalid JSON value.")

    visit(value, 0)
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    require(
        len(raw) <= maximum,
        "JSON exceeds the byte limit.",
        "response_too_large" if maximum == RESULT_LIMIT else "invalid_payload",
    )


def connection_values(connection: dict[str, Any]) -> tuple[dict[str, Any], str]:
    try:
        raw = connection.get("config", {})
        secrets = connection.get("secrets", {})
        require(isinstance(raw, dict) and isinstance(secrets, dict), "Invalid connection.")
        require(
            set(raw)
            <= {
                "realm_id",
                "environment",
                "minor_version",
                "allow_create",
                "allow_update",
                "allow_delete",
                "request_timeout_seconds",
            },
            "Unknown connection configuration.",
        )
        require(set(secrets) == {"access_token"}, "Only a host-injected access token is accepted.")
        config = dict(raw)
        realm = text(config.get("realm_id"), 32)
        require(re.fullmatch(r"[0-9]{1,32}", realm), "Invalid Company ID.")
        config["environment"] = config.get("environment", "sandbox")
        require(config["environment"] in ("sandbox", "production"), "Invalid environment.")
        config["minor_version"] = integer(config.get("minor_version", 75), 75, 999)
        config["request_timeout_seconds"] = integer(
            config.get("request_timeout_seconds", 30), 1, 60
        )
        for key in ("allow_create", "allow_update", "allow_delete"):
            config[key] = config.get(key, True)
            require(type(config[key]) is bool, "Write permissions must be boolean.")
        token = text(secrets.get("access_token"), 8192)
        require(not any(c.isspace() for c in token), "Invalid access token.")
        return config, token
    except (ValueError, TypeError):
        raise Failure(
            "invalid_connection", "Invalid company configuration or scoped access token."
        ) from None
