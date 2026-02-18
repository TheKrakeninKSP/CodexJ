from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from backend.db import get_fs, get_db
from bson import ObjectId
import io
from PIL import Image
import datetime

router = APIRouter()


@router.post("/media/upload")
async def upload_media(file: UploadFile = File(...)):
    fs = get_fs()
    db = get_db()
    if db is None or fs is None:
        raise HTTPException(status_code=503, detail="Database/GridFS not initialized")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    # upload original
    stream = io.BytesIO(data)
    file_id = fs.upload_from_stream(file.filename, stream)

    # create thumbnail (best-effort)
    thumb_id = None
    try:
        img = Image.open(io.BytesIO(data))
        img.thumbnail((300, 300))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        thumb_id = fs.upload_from_stream(f"thumb_{file_id}", buf)
    except Exception:
        thumb_id = None

    meta = {
        "file_id": file_id,
        "thumb_id": thumb_id,
        "filename": file.filename,
        "content_type": file.content_type,
        "uploaded_at": datetime.datetime.utcnow(),
    }
    db.media.insert_one(meta)
    return {"file_id": str(file_id), "thumb_id": str(thumb_id) if thumb_id else None}


@router.get("/media/{media_id}")
def get_media(media_id: str):
    fs = get_fs()
    if fs is None:
        raise HTTPException(status_code=503, detail="GridFS not initialized")
    try:
        fid = ObjectId(media_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    stream = fs.open_download_stream(fid)
    data = stream.read()
    return StreamingResponse(io.BytesIO(data), media_type=stream.content_type or "application/octet-stream")


@router.get("/media/{media_id}/thumb")
def get_thumb(media_id: str):
    db = get_db()
    fs = get_fs()
    if db is None or fs is None:
        raise HTTPException(status_code=503, detail="Database/GridFS not initialized")
    try:
        fid = ObjectId(media_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    meta = db.media.find_one({"file_id": fid})
    if not meta or not meta.get("thumb_id"):
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    stream = fs.open_download_stream(meta["thumb_id"])
    data = stream.read()
    return StreamingResponse(io.BytesIO(data), media_type=stream.content_type or "image/jpeg")
