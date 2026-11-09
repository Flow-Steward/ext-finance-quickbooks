"""HTTP plans and query escaping: removing guards must fail before provider I/O."""

import json
from pathlib import Path

import pytest


def planner():
    from qbo.commands import prepare

    return prepare


@pytest.mark.parametrize(
    ("operation", "method", "endpoint"),
    [
        ("read_invoice", "GET", "/invoice/7"),
        ("read_item", "GET", "/item/7"),
        ("get_customer", "GET", "/customer/7"),
        ("get_company_info", "GET", "/companyinfo/123"),
        ("get_preferences", "GET", "/preferences"),
        ("create_invoice", "POST", "/invoice"),
        ("update_invoice", "POST", "/invoice"),
        ("delete_invoice", "POST", "/invoice"),
    ],
)
def test_native_routes(operation, method, endpoint):
    data = {"Id": "7", "SyncToken": "2", "Line": []}
    if operation.startswith("create_"):
        data = {"Line": []}
    plan = planner()(
        operation,
        {"entity_id": "7", "sync_token": "2", "data": data},
        "123",
    )
    assert plan.method == method
    assert plan.path == endpoint


@pytest.mark.parametrize("entity", ["customer", "vendor", "employee", "item"])
def test_delete_list_entity_is_sparse_inactivation(entity):
    plan = planner()("delete_" + entity, {"entity_id": "7", "sync_token": "2"}, "123")
    assert plan.body == {"Id": "7", "SyncToken": "2", "sparse": True, "Active": False}
    assert plan.query == {"operation": "update"}


def test_delete_and_void_are_explicit():
    delete = planner()("delete_invoice", {"entity_id": "7", "sync_token": "2"}, "123")
    void = planner()(
        "delete_invoice", {"entity_id": "7", "sync_token": "2", "delete_mode": "void"}, "123"
    )
    assert delete.query == {"operation": "delete"}
    assert void.query == {"operation": "void"}


@pytest.mark.parametrize(
    "data", [{"Id": "7"}, {"SyncToken": "2"}, {"Id": "../7", "SyncToken": "2"}]
)
def test_update_requires_valid_id_and_sync_token(data):
    with pytest.raises(ValueError):
        planner()("update_invoice", {"data": data}, "123")


def test_sparse_update_preserves_explicit_version():
    plan = planner()(
        "update_invoice", {"data": {"Id": "7", "SyncToken": "2", "PrivateNote": "x"}}, "123"
    )
    assert plan.body == {"Id": "7", "SyncToken": "2", "PrivateNote": "x", "sparse": True}


def test_search_literal_cannot_escape_query():
    plan = planner()(
        "search_customers",
        {"filters": {"DisplayName": "O'Brien\\test"}, "max_results": 25, "start_position": 26},
        "123",
    )
    assert (
        plan.query["query"]
        == "SELECT * FROM Customer WHERE DisplayName = 'O\\'Brien\\\\test' STARTPOSITION 26 MAXRESULTS 25"
    )


@pytest.mark.parametrize(
    "args",
    [
        {"filters": {"Name OR 1=1": "x"}},
        {"order_by": "Id; DELETE FROM Invoice"},
        {"max_results": True},
        {"start_position": 0},
        {"filters": {"Name": None}},
    ],
)
def test_search_rejects_invalid_query_parts(args):
    with pytest.raises(ValueError):
        planner()("search_customers", args, "123")


def test_advanced_filters_and_sort():
    plan = planner()(
        "search_invoices",
        {
            "filters": {
                "conditions": [
                    {"field": "Balance", "operator": ">", "value": 0},
                    {"field": "CustomerRef", "operator": "IN", "value": ["1", "2"]},
                ]
            },
            "order_by": "TxnDate DESC",
        },
        "123",
    )
    assert "Balance > 0 AND CustomerRef IN ('1', '2') ORDERBY TxnDate DESC" in plan.query["query"]


def test_count_query_does_not_add_pagination():
    plan = planner()("search_invoices", {"count": True}, "123")
    assert plan.query["query"] == "SELECT COUNT(*) FROM Invoice"


def test_balance_sheet_end_date_supplies_year_start():
    plan = planner()("get_balance_sheet", {"options": {"end_date": "2026-10-31"}}, "123")
    assert plan.path == "/reports/BalanceSheet"
    assert plan.query == {"end_date": "2026-10-31", "start_date": "2026-01-01"}


@pytest.mark.parametrize(
    "options",
    [
        {"end_date": "2026-02-30"},
        {"start_date": "2026-11-01", "end_date": "2026-01-01"},
        {"accounting_method": "Whatever"},
        {"requestid": "override"},
    ],
)
def test_invalid_report_options_are_rejected(options):
    with pytest.raises(ValueError):
        planner()("get_profit_and_loss", {"options": options}, "123")


def test_inventory_matches_pinned_upstream():
    root = Path(__file__).resolve().parents[1]
    inventory = json.loads((root / "tests/upstream_inventory.yaml").read_text())
    catalog = json.loads((root / "contracts/catalog.yaml").read_text())
    assert inventory["commit"] == "31a1dd5c3e170e368dbff651abbaf61aabde6ed9"
    assert len(inventory["tools"]) == 142
    assert set(inventory["tools"]) <= set(catalog["operations"])
    for name in inventory["tools"]:
        spec = catalog["operations"][name]
        args = {
            "entity_id": "7",
            "sync_token": "2",
            "data": {"Id": "7", "SyncToken": "2", "FileName": "receipt.pdf"},
        }
        if spec["kind"] == "create":
            args["data"] = {"FileName": "receipt.pdf"}
        plan = planner()(name, args, "123")
        assert plan.path.startswith("/") and not plan.path.startswith("//")
        if spec["kind"] == "report":
            assert plan.path.startswith("/reports/")


@pytest.mark.parametrize("operation", ["delete_payment", "delete_sales_receipt"])
def test_payment_void_uses_sparse_update_include_void(operation):
    plan = planner()(operation, {"entity_id": "7", "sync_token": "2", "delete_mode": "void"}, "123")
    assert plan.query == {"operation": "update", "include": "void"}
    assert plan.body == {"Id": "7", "SyncToken": "2", "sparse": True}


def test_update_explicitly_selects_native_update_operation():
    plan = planner()(
        "update_invoice", {"data": {"Id": "7", "SyncToken": "2", "PrivateNote": "x"}}, "123"
    )
    assert plan.query == {"operation": "update"}
