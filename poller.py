import os
import sys
import time
import json
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_SERVICE_KEY = os.environ['SUPABASE_SERVICE_KEY']
PRODUCT_ID = os.environ['PRODUCT_ID']
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

SB_HEADERS = {
    'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}',
    'apikey': SUPABASE_SERVICE_KEY,
}

REST_URL = f"{SUPABASE_URL}/rest/v1"


def download_file(bucket, file_path):
    if file_path.startswith(bucket + "/"):
        file_path = file_path[len(bucket) + 1:]
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{file_path}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "apikey": SUPABASE_SERVICE_KEY})
    resp.raise_for_status()
    return resp.content


def upload_file(bucket, file_path, content):
    if file_path.startswith(bucket + "/"):
        file_path = file_path[len(bucket) + 1:]
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{file_path}"
    headers = {"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "apikey": SUPABASE_SERVICE_KEY}
    resp = requests.post(url, headers=headers, data=content)
    resp.raise_for_status()
    return resp


def update_job(job_id, data):
    url = f"{REST_URL}/jobs?id=eq.{job_id}"
    headers = {**SB_HEADERS, "Content-Type": "application/json", "Prefer": "return=minimal"}
    return requests.patch(url, headers=headers, json=data)


def create_notification(product_id, customer_id, title, body, ntype):
    try:
        url = "https://njyvnmczoydsaewvfhyq.supabase.co/rest/v1/notifications"
        headers = {**SB_HEADERS, "Content-Type": "application/json", "Prefer": "return=minimal"}
        data = {
            "product_id": product_id,
            "customer_id": customer_id,
            "title": title,
            "body": body,
            "type": ntype,
            "read": False,
        }
        requests.post(url, headers=headers, json=data)
    except Exception:
        pass


def process_job(job):
    job_id = job["id"]
    customer_id = job.get("customer_id")
    input_file_path = job.get("input_file_path")
    if not customer_id:
        raise ValueError("job missing customer_id")
    if not input_file_path:
        raise ValueError("job missing input_file_path")

    file_bytes = download_file("uploads", input_file_path)

    import processor
    records = processor.process_file(file_bytes)

    for r in records:
        record_payload = {
            "product_id": PRODUCT_ID,
            "customer_id": customer_id,
            "title": r["title"],
            "status": r["status"],
            "details": r.get("details", {}),
            "source_file_path": input_file_path,
            "due_date": r.get("due_date"),
        }
        resp = requests.post(
            f"{REST_URL}/records",
            headers={**SB_HEADERS, "Content-Type": "application/json", "Prefer": "return=minimal"},
            json=record_payload,
        )
        resp.raise_for_status()

    results_bucket = "results"
    result_path = f"{job_id}.json"
    result_content = json.dumps(records, default=str).encode("utf-8")
    upload_file(results_bucket, result_path, result_content)

    update_job(job_id, {
        "status": "completed",
        "output_file_path": result_path,
        "result_summary": f"Processed {len(records)} records",
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    create_notification(PRODUCT_ID, customer_id, "Processing complete", "Your upload has been processed successfully.", "success")


def poll():
    while True:
        try:
            url = f"{REST_URL}/jobs?select=*&status=eq.pending&job_type=eq.process_upload&product_id=eq.{PRODUCT_ID}&order=created_at.asc"
            resp = requests.get(url, headers=SB_HEADERS)
            resp.raise_for_status()
            jobs = resp.json()

            for job in jobs:
                try:
                    process_job(job)
                except Exception as e:
                    job_id = job.get("id")
                    customer_id = job.get("customer_id")
                    if job_id:
                        try:
                            update_job(job_id, {
                                "status": "failed",
                                "result_summary": str(e),
                                "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            })
                            if customer_id:
                                create_notification(PRODUCT_ID, customer_id, "Processing failed", "There was an error processing your upload.", "error")
                        except Exception:
                            pass
        except Exception:
            pass
        time.sleep(60)


if __name__ == "__main__":
    print("Poller started")
    poll()
