# QuickBooks Online 1.0.3

Clarify workflow action titles, operation-specific field help and examples. Add a practical workflow action guide. Existing operation contracts and runtime behavior are unchanged.

# QuickBooks Online 1.0.2

- Added automatic shared CI for pull requests and pushes to main, with tests and source-based release packaging.
- Added tag and manual release callers pinned to the shared extension tooling, using this file for the release notes.

## 1.0.1

Clarified the catalog description, supported accounting operations, reports, document handling and company connection setup.

Connect a QuickBooks Online company to Flow Steward for accounting record automation, reporting and document handling. Search and read supported entities such as customers, vendors, accounts, items, invoices, bills, payments and purchase orders, then use the corresponding supported create and update operations to move approved business data into QuickBooks. The release provides 145 workflow operations based on a pinned Intuit tool inventory, implemented through native QuickBooks REST requests.

Financial reporting includes 12 reports covering areas such as profit and loss, balance sheet, cash flow and aged receivables or payables. Reports accept provider options for dates, accounting method and relevant entity filters, and preserve QuickBooks' own report structure and totals. Download invoice PDFs into Flow Steward storage and upload workflow files as QuickBooks attachments, or create attachment metadata without a file.

Use these building blocks to transfer approved invoices, collect balances for follow-up workflows or assemble periodic accounting reports. Searches expose bounded pages and continuation positions. Updates require the current SyncToken to detect conflicting changes, and connection settings can separately disable creates, updates or deletions. Each operation explicitly selects one authorized company and its sandbox or production environment; available entities and behavior depend on the company's plan, region and permissions.

Register an Intuit QuickBooks Online Accounting app, add the Flow Steward callback URL and configure its matching client ID and secret. Create a company connection with the explicit realm ID and sandbox or production environment, authorize that same company and verify the connection.
