import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.db import connect_db, get_db

try:
    connect_db()
    db = get_db()
    print('DB:', type(db), getattr(db, 'name', None))
except Exception as e:
    print('ERROR:', e)
    sys.exit(1)
