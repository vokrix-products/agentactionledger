from processor import process_file, reconcile
from hash_chain import (
    compute_action_id,
    compute_record_hash,
    genesis_prev_hash,
    verify_chain,
    HASH_FIELDS,
)

def test_process_file():
    csv_bytes = b"po_number,amount,date\nPO-001,100.00,2025-01-01\nPO-002,200.00,2025-01-02"
    records = process_file(csv_bytes)
    assert len(records) == 2
    assert records[0]["details"]["po_number"] == "PO-001"
    assert records[0]["status"] == "estimated:info"

    text_bytes = b"hello world"
    records = process_file(text_bytes)
    assert len(records) == 1
    assert records[0]["title"] == "hello world"

def test_reconcile():
    a = [
        {"title": "PO-001", "status": "estimated:info", "details": {"po_number": "PO-001", "amount": "100.00"}, "due_date": None},
        {"title": "PO-002", "status": "estimated:info", "details": {"po_number": "PO-002", "amount": "200.00"}, "due_date": None},
    ]
    b = [
        {"title": "PO-001", "status": "estimated:info", "details": {"po_number": "PO-001", "amount": "100.00"}, "due_date": None},
        {"title": "PO-003", "status": "estimated:info", "details": {"po_number": "PO-003", "amount": "300.00"}, "due_date": None},
    ]
    result = reconcile(a, b)
    assert len(result) == 2
    keys = {r["details"]["key"] for r in result}
    assert "PO-002" in keys
    assert "PO-003" in keys

def test_hash_chain():
    action_id = compute_action_id("zapier", "inst1", "rec1", None)
    assert len(action_id) == 64

    rec = {
        "schema_version": "1.0",
        "action_id": action_id,
        "source_system": "zapier",
        "source_instance_id": "inst1",
        "source_record_id": "rec1",
        "occurred_at": "2025-01-01T00:00:00Z",
        "actor_id": "u1",
        "actor_type": "human",
        "actor_display_name": "User",
        "agent_id": "",
        "agent_name": "",
        "workflow_id": "wf1",
        "workflow_name": "Workflow",
        "tool_name": "",
        "target_resource": "",
        "action_type": "read",
        "outcome": "committed",
        "approver_id": "",
        "approver_name": "",
        "rationale": "",
        "reversal_of_action_id": "",
        "reversal_type": "",
        "source_payload_sha256": "abc",
        "ledger_seq": 1,
        "prev_hash": genesis_prev_hash,
    }
    rec["record_hash"] = compute_record_hash({k: rec[k] for k in HASH_FIELDS})

    status, _ = verify_chain([rec])
    assert status == "verified"

def main():
    test_process_file()
    test_reconcile()
    test_hash_chain()
    print("All tests passed")

if __name__ == "__main__":
    main()
