import os
import io
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from gridfs import GridFSBucket

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "codexj")

_client = None
_db = None
_fs = None

def connect_db():
    global _client, _db, _fs
    if _client:
        return
    _client = MongoClient(MONGO_URI)
    _db = _client[DB_NAME]
    _fs = GridFSBucket(_db)


def close_db():
    global _client
    if _client:
        _client.close()
        _client = None


def get_db():
    return _db


def get_fs():
    return _fs
