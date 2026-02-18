from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.app import app

def run():
    with TestClient(app) as client:
        r = client.get('/')
        print('GET / ->', r.status_code, r.text)
        r = client.post('/api/journals', json={'title': 'tc-journal', 'description': 'from testclient'})
        print('POST /api/journals ->', r.status_code, r.text)

if __name__ == '__main__':
    run()
