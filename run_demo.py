from processor import process_file, reconcile

def main():
    test_bytes = b"supplier,product,price\nAcme,Widget,9.99\nBeta,Gadget,19.99"
    results = process_file(test_bytes)
    assert isinstance(results, list)
    assert len(results) == 2
    assert results[0]["title"] == "Acme"

    records_a = [
        {
            "title": "Acme",
            "status": "estimated:info",
            "details": {"invoice_no": "INV-001", "amount": "100.00"},
            "due_date": None,
        },
        {
            "title": "Beta",
            "status": "estimated:info",
            "details": {"invoice_no": "INV-002", "amount": "50.00"},
            "due_date": None,
        },
    ]
    records_b = [
        {
            "title": "Acme",
            "status": "estimated:info",
            "details": {"invoice_no": "INV-001", "amount": "100.00"},
            "due_date": None,
        }
    ]

    discrepancies = reconcile(records_a, records_b)
    assert len(discrepancies) > 0
    print("Demo completed successfully")

if __name__ == "__main__":
    main()
