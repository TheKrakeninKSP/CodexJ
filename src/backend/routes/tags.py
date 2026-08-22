from fastapi import APIRouter

from backend.database.querying import get_all_tags
from backend.database.structural import TagModel
from backend.models.tag import TagOut

router = APIRouter(prefix="/tags", tags=["tags"])


def _fmt(tag: TagModel) -> TagOut:
    return TagOut(name=tag.name)


@router.get("", response_model=list[TagOut])
async def list_entry_types():
    tags = get_all_tags()
    return [_fmt(tag) for tag in tags]
