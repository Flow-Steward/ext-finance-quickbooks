"""Every catalog operation must traverse the real runtime and HTTP boundary."""

from pathlib import Path
import json
from typing import Any

import pytest
from test_runtime import envelope, invoke

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "contracts/catalog.yaml").read_text())["operations"]


@pytest.mark.parametrize("operation", sorted(n for n, o in CATALOG.items() if o["kind"] != "pdf"))
def test_every_operation_reaches_native_provider_and_normalizes_result(operation):
    spec = CATALOG[operation]
    entity, kind = spec["entity"], spec["kind"]
    args = {"data": {"Id": "7", "SyncToken": "2", "DisplayName": "Example"}, "sync_token": "2"}
    if kind == "create":
        args["data"] = {"DisplayName": "Example", "FileName": "receipt.pdf"}
    response: dict[str, Any]
    if kind == "report":
        response = {
            "Header": {"ReportName": entity},
            "Columns": {"Column": []},
            "Rows": {"Row": []},
        }
    elif kind == "search":
        response = {"QueryResponse": {entity: [{"Id": "7"}]}}
    else:
        response = {entity: {"Id": "7"}}
    result, sent = invoke(envelope(operation, **args), response)
    assert result["ok"] is True, result
    assert sent.call_count == 1
    request = sent.call_args.args[0]
    assert request.get_method() == ("POST" if kind in ("create", "update", "delete") else "GET")
    assert "/v3/company/123/" in request.full_url
    if kind in ("create", "update", "delete"):
        assert "requestid=" in request.full_url
    assert result["result"]["data"] == (
        response if kind == "report" else [{"Id": "7"}] if kind == "search" else {"Id": "7"}
    )
