import requests
import io
from PIL import Image

import os
BASE = os.environ.get('TEST_BASE', 'http://127.0.0.1:8000')


def health_check():
    r = requests.get(f"{BASE}/")
    print("/ ->", r.status_code, r.json())
    r.raise_for_status()


def create_journal(title="Test Journal"):
    r = requests.post(f"{BASE}/api/journals", json={"title": title, "description": "smoke test"})
    print("POST /api/journals ->", r.status_code, r.text)
    r.raise_for_status()
    return r.json()["id"]


def upload_image():
    # Create a small image in memory
    img = Image.new("RGB", (64, 64), color=(200, 150, 100))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    files = {"file": ("smoke.jpg", buf, "image/jpeg")}
    r = requests.post(f"{BASE}/api/media/upload", files=files)
    print("POST /api/media/upload ->", r.status_code, r.text)
    r.raise_for_status()
    return r.json()


def create_entry(journal_id):
    payload = {
        "journal_id": journal_id,
        "body_markdown": "This is a smoke-test entry.",
        "entry_type": "note",
        "custom_fields": {}
    }
    r = requests.post(f"{BASE}/api/journals/{journal_id}/entries", json=payload)
    print(f"POST /api/journals/{journal_id}/entries ->", r.status_code, r.text)
    r.raise_for_status()
    return r.json()


if __name__ == "__main__":
    health_check()
    jid = create_journal()
    media = upload_image()
    entry = create_entry(jid)
    print("Smoke test completed.")
    print("journal_id=", jid)
    print("media=", media)
    print("entry=", entry)
