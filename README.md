# AgentActionLedger

Backend processing modules for the AgentActionLedger product — a hash-chained, tamper-evident action ledger with reconciliation processing. No HTTP server is included in this repo; these are the pure processing primitives consumed by the poller.

## Archetype

**Reconciliation / ledger integrity.** The product ingests two sides of a financial or operational record (buyer reference vs. period document), parses them into normalized records, diffs them, and emits only discrepancies. Every emitted record is anchored into a SHA-256 hash chain so records can be independently verified for tamper-evidence.

## Files

- `processor.py` — `process_file(file_bytes)` handles PDF, Excel, CSV, and plain text. Optional DeepSeek extraction for unstructured text. `reconcile(records_a, records_b)` emits discrepancies.
- `hash_chain.py` — Deterministic action IDs, RFC 8785-style JCS canonicalization, record hash computation, and chain verification.
- `run_demo.py` — Hardcoded demo; zero arguments; parses CSV, runs reconciliation, asserts output.
- `run_tests.py` — Plain-assertion test suite for `process_file`, `reconcile`, and hash-chain functions.

## What the Poller Expects as Input

The poller feeds a single binary file per call into `process_file(file_bytes)`. Accepted formats, tried in order:

1. **PDF** — text extracted with `pdfplumber`, then parsed as delimited rows.
2. **Excel (.xlsx)** — first sheet read with `openpyxl`; first row is treated as the header.
3. **CSV / delimited text** — comma, semicolon, pipe, or tab delimited; first row is the header.
4. **Plain text** — one record per non-empty line, `title` = the line, details = `{"raw": line}`.
5. **Optional DeepSeek** — if `DEEPSEEK_API_KEY` is set and no structured records were found, unstructured text is sent to DeepSeek for extraction.

Each returned record has the shape:

```json
{
  "title": "",
  "status": "estimated:info",
  "details": { "<header>": "<value>", "...": "..." },
  "due_date": "<ISO-8601 date or null>"
}
```

## Expected Inputs (Reconciliation)

Two sides must be provided to `reconcile()`:

- **Side A (reference)**: buyer reference, ledger, rate card, or PO list.
- **Side B (period document)**: statement, invoice, or billed lines.

Both sides are parsed first by `process_file()` into lists of records.

## Matching Key

The first identifier present among:
`invoice_no`, `po_number`, `ref`, `id`, `tracking`, `employee_id`.

Values are normalised before comparison: whitespace stripped, uppercased, and leading zeros dropped.

## Diff Output

`reconcile()` returns only discrepancies — one record per difference, with `details` containing at least:
`key`, `side_a`, `side_b`, `delta`, `side_missing`, and `due_date`.

Status codes emitted:

- `missing_actions:critical` — key present on side A but absent from side B.
- `unexpected_volume:warning` — amount mismatch beyond $0.01, or key present only on side B.
- `stale:warning` — same key, differing dates.

No aggregation or totals are returned.

## Hash Chain

- `compute_action_id(source_system, source_instance_id, source_record_id)` — 64-char SHA-256.
- `compute_record_hash(hash_obj)` — SHA-256 over RFC 8785-style JCS canonical JSON of `HASH_FIELDS`.
- `genesis_prev_hash` — 64 zeros.
- `verify_chain(records)` — returns `("verified", None)`, `("broken", seq)`, or `("empty", None)`.

## Run

```bash
pip install -r requirements.txt
python3 run_demo.py
python3 run_tests.py
```

Dashboard: https://agentactionledger.vokrix.co
Vercel: agentactionledger
Railway: agentactionledger
Cloudflare: agentactionledger.vokrix.co

Landing: https://vokrix.co/agentactionledger
