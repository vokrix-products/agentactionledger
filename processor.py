import csv
import io
import json
import os
import re
from datetime import datetime

import pdfplumber
import openpyxl
from openai import OpenAI

try:
    from hash_chain import compute_action_id
except ImportError:
    compute_action_id = None

IDENTIFIER_KEYS = ["invoice_no", "po_number", "ref", "id", "tracking", "employee_id"]
AMOUNT_KEYS = ["amount", "total", "price", "sum", "value", "amount_usd", "total_usd"]
DATE_KEYS = ["due_date", "date", "occurred_at", "invoice_date", "po_date", "execution_date"]

DEFAULT_STATUS = "estimated:info"

def _strip_leading_zeros(s):
    s = str(s).strip().upper()
    if re.fullmatch(r"0+", s):
        return "0"
    return re.sub(r"^0+", "", s)

def _normalize_identifier(value):
    return _strip_leading_zeros(str(value))

def _pick_due_date(details):
    for key in DATE_KEYS:
        if key in details and details[key]:
            val = str(details[key]).strip()
            if re.match(r"\d{4}-\d{2}-\d{2}", val):
                return val
    return None

def _records_from_rows(rows):
    if not rows:
        return []
    header = [str(h).strip() for h in rows[0]]
    records = []
    for row in rows[1:]:
        if not any(str(cell).strip() for cell in row):
            continue
        details = {}
        for i, h in enumerate(header):
            val = str(row[i]).strip() if i < len(row) else ""
            details[h] = val
        title = str(row[0]).strip() if row else ""
        if not title and len(row) > 1:
            title = str(row[1]).strip()
        if not title:
            title = "unlabeled"
        due = _pick_due_date(details)
        records.append({
            "title": title,
            "status": DEFAULT_STATUS,
            "details": details,
            "due_date": due,
        })
    return records

def _records_from_csv_text(text):
    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;|\t")
        reader = csv.reader(io.StringIO(text), dialect)
        rows = list(reader)
        if len(rows) >= 2:
            return _records_from_rows(rows)
    except Exception:
        pass
    # Treat as plain lines
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        records.append({
            "title": line,
            "status": DEFAULT_STATUS,
            "details": {"raw": line},
            "due_date": None,
        })
    return records

def _extract_with_deepseek(text):
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return []
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    prompt = (
        "Extract a list of action records from the following text. "
        "Each record must have top-level keys: title (the primary entity the buyer tracks: employee name, vendor name, contract party, patient name, etc. NEVER the document type or category), "
        "status (one of: missing_actions:critical, broken:critical, missing_approver:critical, unexpected_volume:warning, missing_rationale:warning, weak:warning, complete:good, verified:good, stale:warning, estimated:info), "
        "details (a flat dictionary of any extra fields), and due_date (ISO-8601 string or null). "
        "Return only a JSON array of such objects, no extra text."
    )
    try:
        resp = client.chat.completions.create(
            model="deepseek-flash",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
        )
        content = resp.choices[0].message.content
        data = json.loads(content)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []

def process_file(file_bytes: bytes) -> list[dict]:
    records = []
    # Try PDF first
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pdf_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        if pdf_text.strip():
            records = _records_from_csv_text(pdf_text)
            if records:
                return records
    except Exception:
        pass

    # Try Excel second
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb.active
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append([str(cell) if cell is not None else "" for cell in row])
        if rows:
            records = _records_from_rows(rows)
            if records:
                return records
    except Exception:
        pass

    # Fallback: decode as UTF-8 text/CSV
    text = ""
    try:
        text = file_bytes.decode("utf-8", errors="ignore")
    except Exception:
        text = file_bytes.decode("latin-1", errors="ignore")
    if text.strip():
        records = _records_from_csv_text(text)
        if records:
            return records

    # Optional DeepSeek extraction for unstructured text
    if not records and text.strip() and os.environ.get("DEEPSEEK_API_KEY"):
        records = _extract_with_deepseek(text)

    return records

def _get_identifier(record):
    details = record.get("details", {})
    for key in IDENTIFIER_KEYS:
        val = details.get(key)
        if val is not None and str(val).strip():
            return _normalize_identifier(str(val))
    title = record.get("title")
    if title:
        return _normalize_identifier(str(title))
    return None

def _get_amount(record):
    details = record.get("details", {})
    for key in AMOUNT_KEYS:
        val = details.get(key)
        if val is not None:
            try:
                return float(str(val).replace(",", "").strip())
            except (ValueError, TypeError):
                continue
    return None

def _get_date(record):
    due = record.get("due_date")
    if due:
        return str(due)
    details = record.get("details", {})
    for key in DATE_KEYS:
        val = details.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None

def reconcile(records_a: list[dict], records_b: list[dict]) -> list[dict]:
    discrepancies = []
    map_a = {}
    map_b = {}

    for rec in records_a:
        key = _get_identifier(rec)
        if key is not None:
            map_a.setdefault(key, []).append(rec)

    for rec in records_b:
        key = _get_identifier(rec)
        if key is not None:
            map_b.setdefault(key, []).append(rec)

    all_keys = set(map_a.keys()) | set(map_b.keys())

    for key in sorted(all_keys):
        a_records = map_a.get(key, [])
        b_records = map_b.get(key, [])

        if a_records and b_records:
            # Key present in both sides: compare amounts with tolerance, then dates
            a = a_records[0]
            b = b_records[0]
            a_amount = _get_amount(a)
            b_amount = _get_amount(b)
            if a_amount is not None and b_amount is not None and abs(a_amount - b_amount) > 0.01:
                delta = round(a_amount - b_amount, 2)
                discrepancies.append({
                    "title": key,
                    "status": "unexpected_volume:warning",
                    "details": {
                        "key": key,
                        "side_a": a,
                        "side_b": b,
                        "delta": delta,
                        "side_missing": None,
                    },
                    "due_date": a.get("due_date") or b.get("due_date") or None,
                })
            else:
                a_date = _get_date(a)
                b_date = _get_date(b)
                if a_date and b_date and a_date != b_date:
                    discrepancies.append({
                        "title": key,
                        "status": "stale:warning",
                        "details": {
                            "key": key,
                            "side_a": a,
                            "side_b": b,
                            "delta": None,
                            "side_missing": None,
                        },
                        "due_date": a.get("due_date") or b.get("due_date") or None,
                    })

        elif a_records and not b_records:
            a = a_records[0]
            discrepancies.append({
                "title": key,
                "status": "missing_actions:critical",
                "details": {
                    "key": key,
                    "side_a": a,
                    "side_b": None,
                    "delta": None,
                    "side_missing": "B",
                },
                "due_date": a.get("due_date") or None,
            })

        elif b_records and not a_records:
            b = b_records[0]
            discrepancies.append({
                "title": key,
                "status": "unexpected_volume:warning",
                "details": {
                    "key": key,
                    "side_a": None,
                    "side_b": b,
                    "delta": None,
                    "side_missing": "A",
                },
                "due_date": b.get("due_date") or None,
            })

    return discrepancies
