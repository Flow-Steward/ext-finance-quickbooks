"""Regenerate declarative host contracts from the pinned operation catalog."""

import json
import pathlib
from typing import Any

root = pathlib.Path(__file__).resolve().parents[1]
catalog = json.loads((root / "contracts/catalog.yaml").read_text())
ops = catalog["operations"]


def dump(path: str, obj: Any) -> None:
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2) + "\n")


errors = [
    "invalid_payload",
    "invalid_connection",
    "effect_claim_required",
    "test_mode_suppressed",
    "write_disabled",
    "provider_unavailable",
    "invalid_provider_response",
    "response_too_large",
    "network_blocked",
    "timeout",
    "authentication_failed",
    "not_found",
    "conflict",
    "rate_limited",
    "provider_validation",
    "artifact_unavailable",
]
con: dict[str, Any] = {
    "name": "connection_ref",
    "value_type": "connection_ref",
    "required": True,
    "display_name": "QuickBooks company",
}


def field(name: str, typ: str = "json", required: bool = False, **schema: Any) -> dict[str, Any]:
    return {
        "name": name,
        "value_type": typ,
        "required": required,
        "display_name": name.replace("_", " ").title(),
        "schema": {
            "type": {
                "text": "string",
                "integer": "integer",
                "json": "object",
                "boolean": "boolean",
                "artifact_handle": "string",
            }[typ],
            **schema,
        },
    }


actions = []
operations = []
forms = []
effects = []
for name, o in sorted(ops.items()):
    kind = o["kind"]
    write = kind in ["create", "update", "delete"]
    ent = o["entity"]
    inputs = [con.copy()]
    if kind in ["get", "read", "pdf"] and ent not in ["CompanyInfo", "Preferences"]:
        inputs.append(field("entity_id", "text", True, minLength=1, maxLength=128))
    if kind == "search":
        inputs += [
            field("filters", "json", False),
            field("start_position", "integer", False, minimum=1, maximum=1000000000),
            field("max_results", "integer", False, minimum=1, maximum=1000),
            field("order_by", "text", False, maxLength=128),
            field("count", "boolean"),
        ]
    if kind in ["create", "update"]:
        inputs.append(field("data", "json", True))
    if kind == "delete":
        inputs += [
            field("entity_id", "text", True, minLength=1, maxLength=128),
            field("sync_token", "text", True, minLength=1, maxLength=32),
            field("delete_mode", "text", False, enum=["delete", "void"]),
        ]
    if kind == "report":
        inputs.append(field("options", "json"))
    if name == "create_attachable":
        inputs.append(field("artifact_handle", "artifact_handle"))
    outputs = [{"name": "data", "value_type": "json"}]
    if kind == "search":
        outputs += [
            {"name": "next_start_position", "value_type": "integer"},
            {"name": "total_count", "value_type": "integer"},
        ]
    if kind == "pdf":
        outputs = [{"name": "pdf_artifact_handle", "value_type": "artifact_handle"}]
    result_fields = ["result." + f["name"] for f in outputs]
    title = name.replace("_", " ").title()
    desc = (
        title
        + ". "
        + (
            "Uses native QuickBooks fields in data. Updates require Id and SyncToken. "
            if write
            else ""
        )
    )
    if kind == "delete":
        desc += "Customer, Vendor, Employee and Item are made inactive. Transaction deletion and voiding are explicit; no fallback."
    operations.append(
        {
            "operation_id": name,
            "display_name": title,
            "description": desc,
            "operation_kind": "action",
            "workflow_visible": True,
            "connection_type_ids": ["quickbooks_company"],
            "category": "accounting",
            "inputs": inputs,
            "outputs": outputs,
            "result_fields": result_fields,
            "error_codes": errors,
        }
    )
    actions.append(
        {
            "action_id": name,
            "workflow_visible": True,
            "title": title,
            "description": desc,
            "required_scopes": ["extension:invoke"],
            "handler": {"mode": "extension"},
            "parameters": [
                {
                    "name": f["name"],
                    "type": {
                        "connection_ref": "string",
                        "artifact_handle": "string",
                        "text": "string",
                        "json": "object",
                        "integer": "integer",
                        "boolean": "boolean",
                    }[f["value_type"]],
                    "required": f["required"],
                }
                for f in inputs
            ],
            "result_fields": result_fields,
            "error_codes": errors,
            "mutates_platform": False,
        }
    )
    forms.append(
        {
            "operation_id": name,
            "title": title,
            "fields": [
                {
                    "name": f["name"],
                    "widget_type": {
                        "artifact_handle": "text",
                        "text": "text",
                        "json": "json",
                        "integer": "integer",
                        "boolean": "boolean",
                    }[f["value_type"]],
                    "label": f["display_name"],
                    "required": f["required"],
                }
                for f in inputs
                if f["name"] != "connection_ref"
            ],
        }
    )
    if write:
        effects.append(
            {
                "operation_id": name,
                "effect_kind": "accounting_write",
                "channel": "quickbooks",
                "idempotency": "required",
                "test_mode_behavior": "suppress",
            }
        )
# Hidden post-connect verifier accepts only the scoped access token and connection config.
actions.append(
    {
        "action_id": "verify_company",
        "title": "Verify company",
        "workflow_visible": False,
        "required_scopes": ["extension:invoke"],
        "handler": {"mode": "extension"},
        "parameters": [],
        "result_fields": [
            "result.subject",
            "result.verified_display_name",
            "result.safe_metadata",
            "result.health",
        ],
        "mutates_platform": False,
    }
)
dump("contracts/operation_manifest.yaml", {"operations": operations})
dump("contracts/step_ui_manifest.yaml", {"forms": forms})
dump("ui/actions/actions.yaml", {"actions": actions})
config = {
    "type": "object",
    "additionalProperties": False,
    "required": ["realm_id"],
    "properties": {
        "realm_id": {"type": "string", "pattern": "^[0-9]{1,32}$"},
        "environment": {"type": "string", "enum": ["sandbox", "production"], "default": "sandbox"},
        "minor_version": {"type": "integer", "minimum": 75, "maximum": 999, "default": 75},
        "allow_create": {"type": "boolean", "default": True},
        "allow_update": {"type": "boolean", "default": True},
        "allow_delete": {"type": "boolean", "default": True},
        "request_timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 60, "default": 30},
    },
}
dump(
    "contracts/connection_types.yaml",
    {
        "connection_types": [
            {
                "connection_type_id": "quickbooks_company",
                "display_name": "QuickBooks Online company",
                "description": "One explicitly selected company. Enter its Company ID (realm ID) before connecting.",
                "auth": {
                    "type": "oauth2",
                    "provider_id": "intuit_oauth",
                    "scopes": {"required": ["com.intuit.quickbooks.accounting"], "optional": []},
                },
                "config_schema": config,
                "secret_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"access_token": {"type": "string"}},
                },
                "capabilities": list(ops),
            }
        ]
    },
)
provider = {
    "provider_id": "intuit_oauth",
    "description": "Authorize one QuickBooks Online company using project-owned Intuit application credentials.",
    "display_name": "Intuit QuickBooks Online",
    "setup_page_id": "setup-guide",
    "help_page_id": "setup-guide",
    "flow": {"type": "authorization_code", "pkce": "none"},
    "credential_fields": [
        {
            "field_id": "client_id",
            "value_type": "text",
            "required": True,
            "secret": False,
            "change_policy": "reauthorization_required",
            "label": "Intuit Client ID",
            "help_text": "Client ID from the Intuit app for the selected sandbox or production environment.",
            "validation": {"min_length": 1, "max_length": 512},
        },
        {
            "field_id": "client_secret",
            "value_type": "secret",
            "required": True,
            "secret": True,
            "change_policy": "reauthorization_required",
            "label": "Intuit Client Secret",
            "help_text": "Matching Intuit app client secret; stored and used only by the platform.",
            "validation": {"min_length": 1, "max_length": 4096},
        },
    ],
    "authorization_endpoint": {"url": "https://appcenter.intuit.com/connect/oauth2"},
    "token_endpoint": {
        "url": "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
        "client_auth_method": "client_secret_basic",
    },
    "revocation_endpoint": {"url": "https://developer.api.intuit.com/v2/oauth2/tokens/revoke"},
    "callback_id": "oauth_authorization",
    "authorization_intents": [{"intent_id": "company_connect", "static_parameters": {}}],
    "post_connect_action_id": "verify_company",
}
v2 = {
    "oauth_providers": [provider],
    "connection_types": "contracts/connection_types.yaml",
    "operation_manifest": "contracts/operation_manifest.yaml",
    "step_ui_manifest": "contracts/step_ui_manifest.yaml",
}
manifest = {
    "manifest_version": 2,
    "extension_id": "flowsteward.quickbooks",
    "kind": "tool_provider",
    "version": "1.0.0",
    "display_name": "QuickBooks Online",
    "description": "Native Python QuickBooks Online accounting integration: all tools from the pinned official MCP server, reports and document artifacts.",
    "lifecycle": {"data_schema_version": 1, "data_migrations": []},
    "vendor": {"name": "Flow Steward"},
    "listing": {
        "category": "finance",
        "tags": ["quickbooks", "accounting", "intuit"],
        "summary": "QuickBooks Online entities, financial reports and attachments.",
    },
    "features": ["tool", "action"],
    "required_scopes": ["extension:invoke", "artifact:read", "artifact:write"],
    "machine_auth": {
        "service_account_key": "svc_ext_quickbooks",
        "required_scopes": ["extension:invoke", "artifact:read", "artifact:write"],
    },
    "egress": {
        "hosts": [
            "quickbooks.api.intuit.com",
            "sandbox-quickbooks.api.intuit.com",
            "appcenter.intuit.com",
            "oauth.platform.intuit.com",
            "developer.api.intuit.com",
        ]
    },
    "account_scope": {
        "scope_type": "project",
        "description": "Each connection grants access to one company in one project.",
    },
    "entrypoint": {"mode": "subprocess", "command": ["python3", "main.py"], "timeout_seconds": 90},
    "health": {"command": ["python3", "health.py"], "timeout_seconds": 5},
    "ui_manifest": "ui/ui_manifest.yaml",
    "action_manifest": "ui/actions/actions.yaml",
    "python_requirements": [],
    "runtime": {"contract_version": "extension_host_v2", "extension_contract_v2": v2},
    "callbacks": [
        {
            "callback_id": "oauth_authorization",
            "purpose": "oauth_authorization",
            "methods": ["GET"],
            "connection_scoped": False,
        }
    ],
    "external_effects": effects,
    "artifact_policies": [
        {
            "operation_id": "get_invoice_pdf",
            "outputs": [
                {
                    "kind": "artifact",
                    "value_type": "artifact_handle",
                    "binding_key": "pdf_artifact_handle",
                    "filename": "invoice.pdf",
                    "content_type": "application/pdf",
                    "max_size_bytes": 20971520,
                    "retention_class": "run_window",
                }
            ],
        },
        {
            "operation_id": "create_attachable",
            "inputs": [
                {
                    "kind": "artifact",
                    "value_type": "artifact_handle",
                    "binding_key": "attachment_input",
                    "from_input": "artifact_handle",
                    "required": False,
                    "max_size_bytes": 104857600,
                }
            ],
        },
    ],
}
dump("extension.yaml", manifest)
dump(
    "extension-descriptor.yaml",
    {
        "schema_version": "extension_descriptor_v1",
        "extension_id": "flowsteward.quickbooks",
        "release_version": "1.0.0",
        "extension_type": "service_extension",
        "artifacts": {
            "skills": [
                {
                    "skill_id": "quickbooks_accounting_workflows",
                    "ref": "artifacts/skills/quickbooks_accounting_workflows.yaml",
                    "publish": True,
                }
            ]
        },
        "identity": {
            "display_name": "QuickBooks Online",
            "description": manifest["description"],
            "tags": ["quickbooks", "accounting"],
        },
        "vendor": {"vendor_name": "Flow Steward"},
        "listing": {"visibility": "public_reference", "category": "finance"},
        "distribution": {
            "channel": "private_byo",
            "execution_modes": ["local"],
            "allows_self_hosted": True,
            "requires_connected_control_plane": False,
            "import_sources": ["file"],
        },
        "runtime": manifest["runtime"],
        "lifecycle": manifest["lifecycle"],
    },
)
dump("ui/ui_manifest.yaml", {"version": "1", "pages": [{"ref": "pages/setup-guide.yaml"}]})
dump(
    "ui/pages/setup-guide.yaml",
    {
        "page_id": "setup-guide",
        "title": "QuickBooks Online setup",
        "description": "Register an Intuit app, enter its credentials and connect a company. See the bundled README for sandbox, production and Company ID instructions.",
        "project_scoped": True,
        "components": [
            {
                "component_id": "quickbooks_setup",
                "type": "markdown",
                "title": "Connect your QuickBooks company",
                "body": "Register a QuickBooks Online Accounting app at https://developer.intuit.com/. Add the exact callback URL shown in the project OAuth setup to the Intuit app. Production requires public HTTPS. Save the matching Client ID and Client Secret in this project. Use development keys for sandbox and production keys for real books.\n\nCreate one company connection, enter its Company ID (realm_id), select its environment, and authorize that same company. The CompanyInfo check confirms access. Add separate connections for additional companies. Select the explicit company connection in each workflow.\n\nUpdates require Id and SyncToken; stale versions return conflict. Customer, Vendor, Employee and Item deletion makes them inactive. Other deletions and voids are explicit. Write categories can be disabled on the connection. Test Run suppresses writes.\n\nTokens are managed by Flow Steward. Never paste refresh tokens or client secrets into workflow inputs. This extension uses the public QuickBooks Accounting API; the Claude cloud connector is not required.",
            }
        ],
    },
)
print(len(ops), "operations")


dump(
    "artifacts/skills/quickbooks_accounting_workflows.yaml",
    {
        "skill_id": "quickbooks_accounting_workflows",
        "version": "1.0.0",
        "display_name": "QuickBooks accounting workflows",
        "description": "Plan company-scoped QuickBooks reports and accounting workflows using the installed extension operations.",
        "enabled": True,
        "category": "finance",
        "instructions": [
            "Discover flowsteward.quickbooks operations and their current input schemas through the platform catalog before building a workflow.",
            "Require an explicit QuickBooks company connection_ref; confirm the company and environment from get_company_info before selecting records.",
            "For financial analysis use get_profit_and_loss, get_balance_sheet, get_cash_flow and aging reports. Preserve provider totals, currency, dates and accounting method in the answer.",
            "Use search operations in bounded pages; follow next_start_position rather than claiming a first page is the complete ledger.",
            "Read an entity before preparing an update or deletion. Keep Id and the observed SyncToken. A conflict requires reviewing the new state; never overwrite it blindly.",
            "Prepare native QBO data with explicit customer, vendor, account, item, currency and tax references. Obtain missing required business facts instead of guessing.",
            "Accounting mutations must run through declared extension operations so the host owns external-effect claims and test suppression. Recording a Payment does not charge a payment card.",
            "Deletion of Customer, Vendor, Employee and Item means inactivation. Select delete or void explicitly for supported transactions; never switch modes after a failure.",
            "Pass document handles from the platform artifact plane; do not supply local filesystem paths, OAuth tokens or arbitrary download URLs.",
            "After a timeout with unknown write outcome, inspect the provider state and retain the original host claim for an authorized retry; do not create a fresh duplicate transaction.",
        ],
        "expected_inputs": [
            {
                "name": "request",
                "type": "paragraph",
                "required": True,
                "description": "The accounting task, company connection, reporting period and any authorized mutation details.",
            }
        ],
        "expected_outputs": [
            {
                "name": "accounting_result",
                "type": "text",
                "required": True,
                "description": "The operation plan or verified provider result with company, period, records and artifact references.",
            }
        ],
        "builder_metadata_jsonb": {
            "purpose": "Use the installed QuickBooks operations accurately in accounting workflows.",
            "use_cases": [
                "financial reports",
                "invoice and bill workflows",
                "accounting record lookup",
            ],
            "anti_use_cases": [
                "QuickBooks Desktop",
                "card payment processing",
                "unapproved accounting changes",
            ],
            "composition_role": "execution",
            "determinism_level": "hybrid",
            "safe_for_auto_use": False,
        },
        "tags": ["quickbooks", "accounting", "workflow"],
    },
)
