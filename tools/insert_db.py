import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.db import connect_db, get_db
from datetime import datetime

connect_db()
db = get_db()
if db is None:
    print('DB not available')
    sys.exit(1)
res = db.journals.insert_one({"title": "direct-insert", "description": "direct", "created_at": datetime.utcnow()})
print('inserted id', res.inserted_id)
