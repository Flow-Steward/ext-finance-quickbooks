"""Host-boundary and provider response tests with HTTP as the only mocked boundary."""

import io
from email.message import Message
import json
from urllib.error import HTTPError, URLError
from unittest.mock import patch

import pytest


def envelope(name="get_customer", **args):
    return {
        "contract_version": "extension_host_v2",
        "mode": "action",
        "runtime_context": {
            "account_id": "a",
            "project_id": "p",
            "workflow_id": "w",
            "job_id": "j",
            "group_id": None,
            "for_each_id": None,
            "step_id": "s",
            "step_execution_id": "e",
            "test_mode": False,
            "external_effect_id": "effect-1",
        },
        "action": {
            "action_id": name,
            "input": {"connection_ref": "company-1", "entity_id": "7", **args},
            "target": {
                "connection": {
                    "connection_id": "company-1",
                    "connection_type": "quickbooks_company",
                    "config": {"realm_id": "123", "environment": "sandbox"},
                    "secrets": {"access_token": "fixture-access-value"},
                }
            },
        },
    }


class Response(io.BytesIO):
    status = 200
    headers = {"Content-Type": "application/json"}


def invoke(payload, response=None):
    from main import handle
    from qbo import transport

    if response is None:
        response = {"Customer": {"Id": "7", "DisplayName": "Test customer"}}
    raw = response if isinstance(response, bytes) else json.dumps(response).encode()
    with (
        patch.object(transport, "resolve_pinned_ips", return_value=("8.8.8.8",)),
        patch.object(transport, "open_pinned_url", return_value=Response(raw)) as send,
    ):
        return handle(payload), send


def test_read_uses_selected_company_and_bearer():
    result, send = invoke(envelope())
    assert result == {
        "ok": True,
        "result": {"data": {"Id": "7", "DisplayName": "Test customer"}},
        "errors": [],
    }
    request = send.call_args.args[0]
    assert (
        request.full_url
        == "https://sandbox-quickbooks.api.intuit.com/v3/company/123/customer/7?minorversion=75"
    )
    assert request.headers["Authorization"] == "Bearer fixture-access-value"


@pytest.mark.parametrize(
    "mutation", ["contract", "scope", "project", "connection", "token", "connection_type"]
)
def test_invalid_host_or_connection_never_calls_provider(mutation):
    p = envelope()
    if mutation == "contract":
        p["contract_version"] = "extension_host_v1"
    if mutation == "scope":
        del p["runtime_context"]["group_id"]
    if mutation == "project":
        p["runtime_context"]["project_id"] = ""
    if mutation == "connection":
        p["action"]["input"]["connection_ref"] = "company-2"
    if mutation == "token":
        p["action"]["target"]["connection"]["secrets"] = {}
    if mutation == "connection_type":
        p["action"]["target"]["connection"]["connection_type"] = "other"
    result, send = invoke(p)
    assert result["ok"] is False
    assert result["definitely_no_external_effect"] is True
    send.assert_not_called()


@pytest.mark.parametrize("mode", ["test", "claim", "disabled"])
def test_write_policy_prevents_provider_call(mode):
    p = envelope("create_customer", data={"DisplayName": "Test"})
    if mode == "test":
        p["runtime_context"]["test_mode"] = True
    if mode == "claim":
        del p["runtime_context"]["external_effect_id"]
    if mode == "disabled":
        p["action"]["target"]["connection"]["config"]["allow_create"] = False
    result, send = invoke(p)
    assert (
        result["error_code"]
        == {
            "test": "test_mode_suppressed",
            "claim": "effect_claim_required",
            "disabled": "write_disabled",
        }[mode]
    )
    send.assert_not_called()


def test_write_request_id_is_stable_and_company_scoped():
    p = envelope("create_customer", data={"DisplayName": "Test"})
    a, one = invoke(p)
    b, two = invoke(p)
    assert a["ok"] and b["ok"]
    assert one.call_args.args[0].full_url == two.call_args.args[0].full_url
    assert "requestid=" in one.call_args.args[0].full_url
    p["action"]["target"]["connection"]["config"]["realm_id"] = "456"
    _, three = invoke(p)
    assert three.call_args.args[0].full_url != one.call_args.args[0].full_url


def test_stale_sync_token_surfaces_conflict_without_retry():
    from main import handle
    from qbo import transport

    fault = {
        "Fault": {
            "Error": [{"code": "5010", "Message": "Stale Object Error"}],
            "type": "ValidationFault",
        }
    }
    with (
        patch.object(transport, "resolve_pinned_ips", return_value=("8.8.8.8",)),
        patch.object(
            transport,
            "open_pinned_url",
            side_effect=HTTPError(
                "https://provider", 400, "Bad", Message(), io.BytesIO(json.dumps(fault).encode())
            ),
        ) as send,
    ):
        result = handle(
            envelope("update_customer", data={"Id": "7", "SyncToken": "2", "DisplayName": "Test"})
        )
    assert result["error_code"] == "conflict"
    assert send.call_count == 1
    assert result["definitely_no_external_effect"] is True


def test_timeout_after_write_reports_unknown_outcome():
    from main import handle
    from qbo import transport

    with (
        patch.object(transport, "resolve_pinned_ips", return_value=("8.8.8.8",)),
        patch.object(
            transport, "open_pinned_url", side_effect=URLError("fixture-access-value")
        ) as send,
    ):
        result = handle(envelope("create_customer", data={"DisplayName": "Test"}))
    assert result["ok"] is False
    assert result["definitely_no_external_effect"] is False
    assert result["external_effect_status"] == "timeout_unknown"
    assert "fixture-access-value" not in json.dumps(result)
    assert send.call_count == 1


def test_search_page_and_count():
    result, _ = invoke(
        envelope("search_customers", max_results=2),
        {
            "QueryResponse": {
                "Customer": [{"Id": "1"}, {"Id": "2"}],
                "startPosition": 1,
                "maxResults": 2,
            }
        },
    )
    assert result["result"]["next_start_position"] == 3
    assert len(result["result"]["data"]) == 2
    result, _ = invoke(
        envelope("search_customers", count=True), {"QueryResponse": {"totalCount": 8}}
    )
    assert result["result"] == {"data": [], "next_start_position": None, "total_count": 8}


@pytest.mark.parametrize("raw", [b"[]", b"not-json", b'{"Fault":{"Error":[{"code":"6000"}]}}'])
def test_invalid_or_fault_response_is_not_success(raw):
    result, _ = invoke(envelope(), raw)
    assert result["ok"] is False


def test_private_dns_is_rejected():
    from main import handle
    from qbo import transport

    with (
        patch.object(transport, "resolve_pinned_ips", return_value=("127.0.0.1",)),
        patch.object(transport, "open_pinned_url") as send,
    ):
        result = handle(envelope())
    assert result["error_code"] == "network_blocked"
    send.assert_not_called()


def test_pdf_is_saved_to_approved_artifact():
    from qbo import documents

    with patch.object(
        documents, "write_artifact_bytes", return_value={"artifact_handle": "artifact:pdf"}
    ) as save:
        result, _ = invoke(envelope("get_invoice_pdf"), b"%PDF-1.4\nfixture")
    assert result["result"] == {"pdf_artifact_handle": "artifact:pdf"}
    assert save.call_args.kwargs["binding_key"] == "pdf_artifact_handle"


def test_attachment_upload_uses_granted_bytes_not_local_paths():
    from qbo import documents

    with patch.object(documents, "read_artifact_bytes", return_value=b"%PDF-1.4\nfixture") as read:
        result, send = invoke(
            envelope(
                "create_attachable",
                data={"FileName": "receipt.pdf", "ContentType": "application/pdf"},
                artifact_handle="artifact:input",
            ),
            {"AttachableResponse": [{"Attachable": {"Id": "9"}}]},
        )
    assert result["ok"] is True
    assert read.call_args.kwargs["binding_key"] == "attachment_input"
    request = send.call_args.args[0]
    assert "/upload?" in request.full_url
    assert b"%PDF-1.4" in request.data
    assert "multipart/form-data" in request.headers["Content-type"]


def test_attachment_item_fault_is_not_success():
    result, _ = invoke(
        envelope("create_attachable", data={"FileName": "a.pdf"}),
        {"AttachableResponse": [{"Fault": {"Error": [{"code": "6000"}]}}]},
    )
    assert result["ok"] is False


def test_company_identity_is_verified_before_success():
    p = envelope("verify_company")
    p["action"]["input"] = {}
    result, _ = invoke(
        p, {"CompanyInfo": {"Id": "1", "CompanyName": "Example UK", "Country": "GB"}}
    )
    assert result["result"]["subject"] == "sandbox:123"
    assert result["result"]["verified_display_name"] == "Example UK"
    result, _ = invoke(p, {"CompanyInfo": {"Id": "1"}})
    assert result["ok"] is False
