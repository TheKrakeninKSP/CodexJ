import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import requests

BASE = os.environ.get('TEST_BASE', 'http://127.0.0.1:8000')

def run():
    r = requests.post(f"{BASE}/api/journals", json={"title": "Debug Journal", "description": "debug"})
    print('status', r.status_code)
    print('text:', r.text)
    try:
        print('json:', r.json())
    except Exception as e:
        print('no json:', e)

if __name__ == '__main__':
    run()
