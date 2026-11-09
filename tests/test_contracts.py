"""The workflow catalog exposes each provider capability with matching schemas."""

import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT / path).read_text())


def test_action_projection_and_effects_are_complete():
    ops = {o["operation_id"]: o for o in read("contracts/operation_manifest.yaml")["operations"]}
    actions = {
        o["action_id"]: o
        for o in read("ui/actions/actions.yaml")["actions"]
        if o["workflow_visible"]
    }
    assert len(ops) == 145
    assert set(ops) == set(actions)
    effects = {e["operation_id"] for e in read("extension.yaml")["external_effects"]}
    assert effects == {n for n in ops if n.startswith(("create_", "update_", "delete_"))}
    for n in ops:
        assert ops[n]["result_fields"] == actions[n]["result_fields"]
        assert "connection_ref" in {p["name"] for p in actions[n]["parameters"]}


def test_connection_disallows_arbitrary_urls_and_secrets():
    con = read("contracts/connection_types.yaml")["connection_types"][0]
    jsonschema.validate({"realm_id": "123", "environment": "production"}, con["config_schema"])
    for value in [
        {"realm_id": "123", "base_url": "https://evil.invalid"},
        {"realm_id": "../123"},
        {"realm_id": "123", "allow_delete": "false"},
    ]:
        try:
            jsonschema.validate(value, con["config_schema"])
        except jsonschema.ValidationError:
            pass
        else:
            raise AssertionError("Unsafe configuration accepted")
    assert set(con["secret_schema"]["properties"]) == {"access_token"}


def test_oauth_uses_host_managed_secret_basic_and_fixed_endpoints():
    provider = read("extension.yaml")["runtime"]["extension_contract_v2"]["oauth_providers"][0]
    assert provider["token_endpoint"] == {
        "url": "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
        "client_auth_method": "client_secret_basic",
    }
    assert provider["post_connect_action_id"] == "verify_company"
    assert read("extension.yaml")["python_requirements"] == []
