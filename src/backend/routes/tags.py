from fastapi import APIRouter, HTTPException

from backend.database.querying import create_tag as create_tag_record
from backend.database.querying import get_all_tags, get_tag_by_name
from backend.database.structural import TagModel
from backend.models.tag import TagOut
from backend.utils.common import utcnow

router = APIRouter(prefix="/tags", tags=["tags"])


def _fmt(tag: TagModel) -> TagOut:
    return TagOut(id=tag.id, name=tag.name)


@router.get("", response_model=list[TagOut])
async def list_tags():
    tags = get_all_tags()
    return [_fmt(tag) for tag in tags]


@router.post("", response_model=TagOut, status_code=201)
async def create_tag(name: str):
    if get_tag_by_name(name) is not None:
        raise HTTPException(status_code=400, detail="Tag already exists")
    tag = TagModel(name=name, created_at=utcnow())
    tag_id = create_tag_record(tag)
    if not tag_id:
        raise HTTPException(status_code=500, detail="Failed to create tag")
    tag.id = tag_id
    return _fmt(tag)
