from fastapi import APIRouter, Depends, HTTPException

from backend.database.querying import create_tag as create_tag_record
from backend.database.querying import get_tag_by_name, get_tags_by_user
from backend.database.structural import TagModel, UserModel
from backend.models.tag import TagCreate, TagOut
from backend.utils.auth import get_current_user
from backend.utils.common import utcnow

router = APIRouter(prefix="/tags", tags=["tags"])


def _fmt(tag: TagModel) -> TagOut:
    return TagOut(id=tag.id, name=tag.name)


@router.get("", response_model=list[TagOut])
async def list_tags(user: UserModel = Depends(get_current_user)):
    return [_fmt(tag) for tag in get_tags_by_user(user.id)]


@router.post("", response_model=TagOut, status_code=201)
async def create_tag(
    tag_payload: TagCreate,
    user: UserModel = Depends(get_current_user),
):
    name = tag_payload.name
    if get_tag_by_name(user.id, name) is not None:
        raise HTTPException(status_code=400, detail="Tag already exists")
    tag = TagModel(user_id=user.id, name=name, created_at=utcnow())
    tag_id = create_tag_record(tag)
    if not tag_id:
        raise HTTPException(status_code=500, detail="Failed to create tag")
    tag.id = tag_id
    return _fmt(tag)
