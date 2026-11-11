# QuickBooks Online for Flow Steward

Connect a QuickBooks Online company to Flow Steward for accounting record automation, reporting and document handling. Search and read supported entities such as customers, vendors, accounts, items, invoices, bills, payments and purchase orders, then use the corresponding supported create and update operations to move approved business data into QuickBooks. The release provides 145 workflow operations based on a pinned Intuit tool inventory, implemented through native QuickBooks REST requests.

Financial reporting includes 12 reports covering areas such as profit and loss, balance sheet, cash flow and aged receivables or payables. Reports accept provider options for dates, accounting method and relevant entity filters, and preserve QuickBooks' own report structure and totals. Download invoice PDFs into Flow Steward storage and upload workflow files as QuickBooks attachments, or create attachment metadata without a file.

Use these building blocks to transfer approved invoices, collect balances for follow-up workflows or assemble periodic accounting reports. Searches expose bounded pages and continuation positions. Updates require the current SyncToken to detect conflicting changes, and connection settings can separately disable creates, updates or deletions. Each operation explicitly selects one authorized company and its sandbox or production environment; available entities and behavior depend on the company's plan, region and permissions.

Register an Intuit QuickBooks Online Accounting app, add the Flow Steward callback URL and configure its matching client ID and secret. Create a company connection with the explicit realm ID and sandbox or production environment, authorize that same company and verify the connection.

The upstream reference is Intuit's MIT-licensed MCP server at
https://github.com/intuit/quickbooks-online-mcp-server/tree/31a1dd5c3e170e368dbff651abbaf61aabde6ed9.
Its README says 145 tools / 29 entities; this revision actually contains 142 tool
files, including Budget search and Preferences. All 142 are represented here,
plus `get_invoice`, `get_item` and `get_aged_receivables_detail` (145 workflow
operations total). The 11 upstream reports are included; the additional aging
detail report makes 12. See `COVERAGE.md` for the exact correspondence.

## Connect a company

1. Register a QuickBooks Online Accounting app at https://developer.intuit.com/.
2. Copy the exact Flow Steward callback URL from the extension's project Setup
   form into the Intuit app's redirect URIs. Production needs public HTTPS.
3. Save the matching Client ID and Client Secret in the extension's project
   OAuth configuration. Development keys work with sandbox companies;
   production keys work with production companies. Keep separate configurations
   for these environments.
4. Create a **QuickBooks Online company** connection. Enter `realm_id` (the
   QuickBooks Company ID), select `sandbox` or `production`, and authorize the
   same company in Intuit. Company ID is available in QuickBooks account/billing
   settings and in Intuit's sandbox dashboard; treat it as a string.
5. The extension verifies CompanyInfo using the granted token and the configured
   company ID. A mismatched or inaccessible company cannot pass verification.
6. Select this explicit connection in each workflow operation. Add a separate
   connection for each additional company; there is no default company.

Company ID is deliberately explicit: the current host OAuth contract does not
expose Intuit's unsigned `realmId` callback parameter to extensions. No callback
code, Client Secret, refresh token or OAuth state is passed to this runtime.
Core stores and rotates OAuth credentials, handles reconnect/disconnect, and
injects only the selected connection's access token. The Accounting scope is
`com.intuit.quickbooks.accounting`; local write controls do not reduce Intuit's
provider-side OAuth scope.

## Workflow inputs

Every operation requires `connection_ref`. Single-entity reads use `entity_id`.
`get_company_info` uses the connection's company ID, and `get_preferences` needs
no entity ID. Results use `result.data` with native QuickBooks fields.

Create/update operations accept `data`, a JSON object using native QBO field
names. This retains all fields, including country-specific taxes, references,
addresses, currency and line details without a lossy translation layer.
For example `create_customer` takes `{"DisplayName":"Example customer"}`;
`create_invoice` takes `{"CustomerRef":{"value":"1"},"Line":[{"Amount":100,
"DetailType":"SalesItemLineDetail","SalesItemLineDetail":{"ItemRef":{"value":"1"}}}]}`.
Provider entity validation and availability still depend on the company, plan,
country and QuickBooks API permissions.

Updates require `data.Id` and the current `data.SyncToken`. Sparse updates are
the default; `sparse:false` explicitly requests a full update. A stale version
returns `conflict`; the extension never silently fetches a newer version and
overwrites concurrent changes. Use the read operation and review the new value.

Delete operations require `entity_id` and `sync_token`. Customer, Vendor,
Employee and Item deletion means sparse `Active:false` inactivation. Other
entities use QuickBooks' delete operation. `delete_mode: void` explicitly
voids an Invoice, Payment or SalesReceipt. There is no delete-to-void fallback.
QuickBooks may refuse operations according to entity state or country rules.

Writes require a durable host external-effect claim, use a stable provider
`requestid`, and are suppressed in Test Run. `allow_create`, `allow_update` and
`allow_delete` may be disabled independently on a connection. There are no
automatic network retries; an uncertain write outcome is reported explicitly.

## Search and reports

Search uses one bounded page: `max_results` (1–1000, default 100),
`start_position` (1-based), optional `order_by` such as `TxnDate DESC`, and
`filters` such as `{"DisplayName":"Example customer"}`. Advanced filters use
`{"conditions":[{"field":"Balance","operator":">","value":0}]}`. Supported
operators: `=`, `!=`, `<`, `>`, `<=`, `>=`, `LIKE`, `IN`. Values are escaped;
raw SQL, arbitrary endpoints, OR expressions and automatic fetch-all are not
accepted. QuickBooks decides which fields an entity can filter/sort. Use
`result.next_start_position` for the next page; a full final page can produce
one extra empty request. `count:true` returns `result.total_count`.

Reports accept `options` with API query names: date ranges, accounting method,
customer/vendor/account/item/class/department filters, aging parameters and
column summarization. Invalid dates and reversed date ranges fail locally.
Balance Sheet supplies January 1 of the end-date year when only end_date is
specified, matching the upstream fix. Output retains Header, Columns and Rows;
the extension never recalculates financial totals.

## Documents

`get_invoice_pdf` saves provider PDF bytes as the host-granted
`result.pdf_artifact_handle` (maximum 20 MiB). It cannot write arbitrary local
paths. `create_attachable` accepts native metadata in `data` and an optional
`artifact_handle`; the platform-granted artifact is uploaded as multipart data.
Omit the handle for metadata-only creation. Use a preceding file-transfer step
for local or remote files, rather than giving this extension filesystem paths
or arbitrary download URLs. Uploaded files are bounded by the declared artifact
policy. `get_attachable` returns metadata; temporary provider URLs are not fetched.

## Runtime and development

CPython 3.12 and the host's public `flowsteward_extension_sdk` 0.4.0 are required.
There are no additional third-party runtime dependencies and no platform-specific
wheels. The bundle is architecture-neutral; this does not claim a live
installation was tested on both architectures.

From the Flow Steward application checkout, run:

```sh
./core/entrypoints/cli/scripts/lint.sh --checks extension-static,extension-tests --extension-root /absolute/path/to/flowsteward_quickbooks
```

Health is offline bundle integrity, not proof of an authenticated company.
Live API behavior requires an Intuit sandbox grant; offline tests exercise the
real request planner, runtime and transport with the HTTP boundary simulated.
The hosted Claude connector is a separate product and is not used by this bundle.
QuickBooks Desktop, payroll execution, payment processing and private cloud-only
benchmarking features are outside the official Accounting MCP reference scope.

To export with the current public CLI, pass the release version explicitly:

```sh
./flow-steward extensions bundle flowsteward.quickbooks --root extensions --extension-version 1.0.2 --output-dir dist/extensions --non-interactive --confirm
```

This exports a package; installation and catalog publication are separate operations.

The operation source of truth is `contracts/catalog.yaml`, stored in the
JSON-compatible YAML subset so the runtime needs no YAML dependency. After
changing it, run `python3 scripts/generate_contracts.py` to regenerate the
manifest, workflow/action schemas and setup page. `tests/upstream_inventory.yaml`
pins the independent reference-tool inventory; update it only when deliberately
moving to another upstream revision. `COVERAGE.md` records the original source
path for each operation.

The descriptor also includes **QuickBooks accounting workflows**, a registry skill
that guides company selection, operation discovery, report interpretation,
pagination, safe updates and document handling through the existing operations.

## CI and releases

Pull requests and pushes to `main` run the shared extension build workflow. The
repository recipe is `.github/release-config.json`: it selects the test
requirements, test paths and portable source package. Shared tooling installs
the verified Flow Steward extension SDK wheel before the development requirements.

After the release changes are merged, create a new tag matching `extension.yaml`:

```sh
git tag v1.0.2
git push origin v1.0.2
```

To run the same release pipeline manually for that immutable tag:

```sh
gh workflow run release.yml --ref main -f tag=v1.0.2
```

The release caller builds, tests and packages the tagged source through the shared
workflow. Keep published tags immutable; release a new patch version for later
changes rather than moving an existing tag or uploading a replacement ZIP.
