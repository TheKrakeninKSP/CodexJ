from fastapi import APIRouter, HTTPException
from fastapi import status
from backend.db import get_db
from bson import ObjectId
from backend.models import JournalCreate, EntryCreate
from datetime import datetime

router = APIRouter()


@router.post("/journals", status_code=status.HTTP_201_CREATED)
def create_journal(payload: JournalCreate):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    doc = {
        "title": payload.title,
        "description": payload.description,
        "created_at": datetime.utcnow(),
    }
    res = db.journals.insert_one(doc)
    # pymongo may add an ObjectId to the original dict; remove it and return string id
    doc_id = res.inserted_id
    doc.pop("_id", None)
    doc["id"] = str(doc_id)
    return doc


@router.get("/journals")
def list_journals():
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    items = []
    for d in db.journals.find().sort("created_at", -1):
        d["id"] = str(d["_id"])
        d.pop("_id", None)
        items.append(d)
    return items


@router.post("/journals/{journal_id}/entries", status_code=status.HTTP_201_CREATED)
def create_entry(journal_id: str, payload: EntryCreate):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    if not ObjectId.is_valid(journal_id):
        raise HTTPException(status_code=400, detail="Invalid journal id")
    doc = {
        "journal_id": ObjectId(journal_id),
        "body_markdown": payload.body_markdown,
        "entry_type": payload.entry_type,
        "custom_fields": payload.custom_fields or {},
        "media_ids": [],
        "created_at": datetime.utcnow(),
    }
    res = db.entries.insert_one(doc)
    entry_id = res.inserted_id
    # remove any ObjectId left in doc and return string ids
    doc.pop("_id", None)
    doc["id"] = str(entry_id)
    doc["journal_id"] = journal_id
    return doc


@router.get("/journals/{journal_id}/entries")
def list_entries(journal_id: str):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    if not ObjectId.is_valid(journal_id):
        raise HTTPException(status_code=400, detail="Invalid journal id")
    items = []
    for d in db.entries.find({"journal_id": ObjectId(journal_id)}).sort("created_at", -1):
        d["id"] = str(d["_id"])
        d["journal_id"] = str(d["journal_id"])
        d.pop("_id", None)
        items.append(d)
    return items
