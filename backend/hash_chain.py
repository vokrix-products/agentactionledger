import hashlib
import json

HASH_FIELDS = [
    "schema_version",
    "action_id",
    "source_system",
    "source_instance_id",
    "source_record_id",
    "occurred_at",
    "actor_id",
    "actor_type",
    "actor_display_name",
    "agent_id",
    "agent_name",
    "workflow_id",
    "workflow_name",
    "tool_name",
    "target_resource",
    "action_type",
    "outcome",
    "approver_id",
    "approver_name",
    "rationale",
    "reversal_of_action_id",
    "reversal_type",
    "source_payload_sha256",
    "ledger_seq",
    "prev_hash",
]

genesis_prev_hash = "0" * 64

def compute_action_id(source_system: str, source_instance_id: str, source_record_id: str, source_payload_sha256: str = None) -> str:
    if source_record_id:
        raw = f"{source_system}|{source_instance_id}|{source_record_id}"
    elif source_payload_sha256:
        raw = source_payload_sha256
    else:
        raw = f"{source_system}|{source_instance_id}|"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def canonical_json(obj):
    """RFC 8785-style JCS canonicalization for JSON-compatible data."""
    if isinstance(obj, dict):
        items = sorted(obj.items(), key=lambda x: x[0])
        return "{" + ",".join(f'"{k}":{canonical_json(v)}' for k, v in items) + "}"
    elif isinstance(obj, list):
        return "[" + ",".join(canonical_json(item) for item in obj) + "]"
    elif isinstance(obj, str):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    elif obj is None:
        return "null"
    elif isinstance(obj, bool):
        return "true" if obj else "false"
    elif isinstance(obj, (int, float)):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    else:
        return json.dumps(str(obj), ensure_ascii=False, separators=(",", ":"))

def compute_record_hash(hash_obj: dict) -> str:
    canonical = canonical_json(hash_obj).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()

def verify_chain(records: list):
    if not records:
        return ("empty", None)

    prev = genesis_prev_hash
    for idx, rec in enumerate(records, start=1):
        if rec.get("prev_hash") != prev:
            return ("broken", idx)

        hash_obj = {k: rec.get(k) for k in HASH_FIELDS if k in rec}
        if compute_record_hash(hash_obj) != rec.get("record_hash"):
            return ("broken", idx)

        ledger_seq = rec.get("ledger_seq")
        if ledger_seq is None:
            return ("broken", idx)
        try:
            if int(ledger_seq) != idx:
                return ("broken", idx)
        except (TypeError, ValueError):
            return ("broken", idx)

        prev = rec.get("record_hash")

    return ("verified", None)
