from fastapi import APIRouter, Depends

from backend.database.querying import get_all_users, get_entry_stats_by_user
from backend.models.admin import AdminOverviewResponse, AdminUserStats
from backend.utils.addressing import get_user_media_path
from backend.utils.auth import require_admin
from backend.utils.storage import dir_usage

router = APIRouter(prefix="/admin", tags=["admin"])


# Plain `def` so FastAPI runs it in the threadpool - the disk walk blocks.
@router.get("/overview", response_model=AdminOverviewResponse)
def admin_overview(_=Depends(require_admin)):
    entry_stats = get_entry_stats_by_user()
    users: list[AdminUserStats] = []
    for user in get_all_users():
        media_files, media_bytes = dir_usage(get_user_media_path(user.id))
        entry_count, text_bytes = entry_stats.get(user.id, (0, 0))
        users.append(
            AdminUserStats(
                id=user.id,
                username=user.username,
                is_admin=user.is_admin,
                created_at=user.created_at,
                last_login_at=user.last_login_at,
                entry_count=entry_count,
                media_files=media_files,
                media_bytes=media_bytes,
                text_bytes=text_bytes,
                total_bytes=media_bytes + text_bytes,
            )
        )

    total_media = sum(u.media_bytes for u in users)
    total_text = sum(u.text_bytes for u in users)
    return AdminOverviewResponse(
        user_count=len(users),
        total_media_bytes=total_media,
        total_text_bytes=total_text,
        total_bytes=total_media + total_text,
        users=users,
    )
