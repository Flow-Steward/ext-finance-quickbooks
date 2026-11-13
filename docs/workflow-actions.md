# QuickBooks Online workflow actions

Every action selects one connected QuickBooks company. Action IDs in parentheses
remain compatible with saved workflows; the builder titles describe the result.

## Connect the intended company

Register an Intuit Accounting app, configure its matching client ID/secret and
exact Flow Steward callback URL, then create a project company connection. Enter
the realm ID and choose sandbox or production before authorization. Authorize that
same company and verify the connection. Create, update and delete permissions can
be disabled separately in the connection; Intuit plan, region and user permissions
also determine which records and reports are available.

## Search, inspect and update a customer

1. Add **Search customer records** (`search_customers`) and select the connection.
2. In **Search filters (JSON)**, use a QuickBooks filterable field, for example:

   ```json
   {"DisplayName":"Example customer Ltd"}
   ```

3. Leave **Count only** off to retrieve records. Set **Maximum records per page**
   to 100. Pass `next_start_position` to **First result position** to read a later
   page; positions start at 1. A count query returns `total_count` instead.
4. Use **Read customer** (`get_customer`) with the returned ID to inspect its
   latest `Id` and `SyncToken` before editing.
5. Add **Update customer** (`update_customer`), with **Data (QuickBooks JSON)**:

   ```json
   {"Id":"123","SyncToken":"0","DisplayName":"Updated customer Ltd"}
   ```

Replace 123 and 0 with the current record's values from the same company. The
runtime defaults to a sparse update, preserving omitted fields. A stale SyncToken
can produce a conflict: read the current record and review the change before
trying again. A create action instead requires the entity's native required fields
and rejects Id/SyncToken; **Create customer** (`create_customer`) can use
`{"DisplayName":"Example customer Ltd"}` in a company where that name is unused.

Filters also support explicit conditions, for example
`{"conditions":[{"field":"Id","operator":"IN","value":["123","456"]}]}`.
Conditions use AND. Field names, supported operators and sortable fields must be
valid for the chosen QuickBooks entity; the connector does not accept raw SQL.

## Create invoices, bills and other accounting records

Choose the action for the exact entity, such as **Create invoice**
(`create_invoice`) or **Create bill** (`create_bill`). **Data (QuickBooks JSON)** is
a native provider object, not a Flow Steward order object. Resolve customer/vendor,
account, item and tax references in earlier steps, then build the entity's required
lines and references. Read/search outputs retain the provider's field names.

## Reports and document files

- Report actions, such as **Read profit and loss report** (`get_profit_and_loss`),
  accept **Report options (JSON)**. For a period report:
  `{"start_date":"2026-01-01","end_date":"2026-01-31","accounting_method":"Accrual"}`.
  The selected report determines which options apply; results retain QuickBooks'
  own structure and totals. The accounting method is Cash or Accrual.
- **Download invoice PDF** (`get_invoice_pdf`) takes the invoice's QuickBooks ID
  and returns `pdf_artifact_handle` for a later file/email/archive step.
- **Create attachment or upload a file** (`create_attachable`) takes attachment
  metadata in **Data (QuickBooks JSON)**. With **Workflow file handle**, supply
  `FileName` (a plain filename), a supported `ContentType` such as `application/pdf`
  and the desired `AttachableRef` records. The file must come from a previous
  workflow step. Without a file handle, the action creates metadata only.

## Remove or void a record

For Customer, Vendor, Employee and Item, the delete action makes the record
inactive. Set the ID and current SyncToken and use deletion mode `delete`.
Invoice, Payment and SalesReceipt also support explicit `void`; other supported
delete actions reject void. There is no fallback from a rejected deletion to
another kind of mutation. Review the selected record before running a removal.

Write actions are suppressed in workflow test mode; reads still contact
QuickBooks. If a write loses its response, inspect the provider and reported effect
status before rerunning it: the accounting record may already have changed.
