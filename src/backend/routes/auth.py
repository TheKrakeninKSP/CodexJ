import os
import secrets
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError

from backend.constants import DEFAULT_COLOR_THEME, DEFAULT_WORKSPACE_NAME
from backend.database.querying import (
    create_user,
    create_workspace,
    get_entry_stats_by_user,
    get_user_account_counts,
    get_user_by_username,
    record_user_login,
    update_user_theme,
)
from backend.database.structural import UserModel, WorkspaceModel
from backend.models.auth import (
    AccountStatsResponse,
    DeleteUserResponse,
    CurrentUserResponse,
    ImportResult,
    LoginRequest,
    PrivilegedModeRequest,
    PrivilegedModeResponse,
    PrivilegedStatusResponse,
    RegisterResponse,
    RegisterWithImportResponse,
    TokenResponse,
    UnlockRequest,
    UpdateUserPreferencesRequest,
    UserPreferencesResponse,
)
from backend.models.data_management import UserDataDump
from backend.models.user import UserCreate
from backend.utils.addressing import get_user_media_path
from backend.utils.auth import (
    create_access_token,
    get_current_user,
    hash_secret,
    require_privileged_mode,
    set_privileged_mode,
    verify_secret,
)
from backend.utils.storage import dir_usage
from backend.utils.common import utcnow
from backend.utils.data_management import (
    derive_dump_key,
    import_dump_data,
    read_dump_meta,
    read_encrypted_dump,
    recursive_delete_user,
    validate_dump_structure,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(payload: UserCreate):
    if get_user_by_username(payload.username) is not None:
        raise HTTPException(status_code=409, detail="Username already taken")

    # Generate a one-time hashkey (32 random bytes → 64-char hex string)
    plaintext_hashkey = secrets.token_hex(32)
    # Generate a dump key derived from the hashkey and username for exports
    dump_key = derive_dump_key(plaintext_hashkey, payload.username)

    user = UserModel(
        username=payload.username,
        password_hash=hash_secret(payload.password),
        hashkey_hash=hash_secret(plaintext_hashkey),
        dump_key=dump_key,
        theme=DEFAULT_COLOR_THEME.value,
        created_at=utcnow(),
    )
    user_id = create_user(user)

    default_workspace = WorkspaceModel(
        user_id=user_id,
        name=DEFAULT_WORKSPACE_NAME,
        created_at=utcnow(),
    )
    create_workspace(default_workspace)
    record_user_login(user_id)

    token = create_access_token(user_id, payload.username)
    return RegisterResponse(
        username=payload.username,
        access_token=token,
        hashkey=plaintext_hashkey,
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    user = get_user_by_username(payload.username)
    if not user or not verify_secret(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    record_user_login(user.id)
    token = create_access_token(user.id, user.username)
    return TokenResponse(access_token=token)


@router.post("/unlock", response_model=TokenResponse)
async def unlock(payload: UnlockRequest):
    user = get_user_by_username(payload.username)
    if not user or not verify_secret(payload.hashkey, user.hashkey_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or hashkey",
        )
    record_user_login(user.id)
    token = create_access_token(user.id, user.username)
    return TokenResponse(access_token=token)


@router.post("/privileged", response_model=PrivilegedModeResponse)
async def enable_privileged_mode(
    payload: PrivilegedModeRequest,
    user: UserModel = Depends(get_current_user),
):
    if not verify_secret(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password",
        )
    set_privileged_mode(True)
    return PrivilegedModeResponse(status="Privileged mode enabled")


@router.get("/privileged", response_model=PrivilegedStatusResponse)
async def get_privileged_mode_status(_=Depends(get_current_user)):
    from backend.globalvar import IS_SESSION_PRIVILEGED

    return PrivilegedStatusResponse(is_privileged=IS_SESSION_PRIVILEGED)


@router.post("/privileged/disable", response_model=PrivilegedModeResponse)
async def disable_privileged_mode():
    set_privileged_mode(False)
    return PrivilegedModeResponse(status="Privileged mode disabled")


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(user: UserModel = Depends(get_current_user)):
    return CurrentUserResponse(username=user.username, is_admin=user.is_admin)


# Plain `def` so FastAPI runs it in the threadpool - the disk walk blocks.
@router.get("/me/stats", response_model=AccountStatsResponse)
def get_my_stats(user: UserModel = Depends(get_current_user)):
    _media_files, media_bytes = dir_usage(get_user_media_path(user.id))
    _entries, text_bytes = get_entry_stats_by_user(user.id).get(user.id, (0, 0))
    return AccountStatsResponse(
        created_at=user.created_at,
        **get_user_account_counts(user.id),
        media_bytes=media_bytes,
        text_bytes=text_bytes,
        total_bytes=media_bytes + text_bytes,
    )


@router.get("/preferences", response_model=UserPreferencesResponse)
async def get_user_preferences(
    user: UserModel = Depends(get_current_user),
):
    return UserPreferencesResponse(theme=user.theme)


@router.patch("/preferences", response_model=UserPreferencesResponse)
async def update_user_preferences(
    payload: UpdateUserPreferencesRequest,
    user: UserModel = Depends(get_current_user),
):
    theme = payload.theme
    user_id = user.id
    updated = update_user_theme(user_id, theme)
    if not updated:
        raise HTTPException(
            status_code=404, detail="Failed to updated user preferences"
        )
    return UserPreferencesResponse(theme=theme)


@router.delete("/delete", response_model=DeleteUserResponse)
async def delete_user(
    user: UserModel = Depends(get_current_user),
    _=Depends(require_privileged_mode),
):
    """Delete user account and all associated data."""
    user_id = user.id

    await recursive_delete_user(user_id)

    # Delete user's media directory if it exists
    user_media_dir = get_user_media_path(user_id)
    if os.path.exists(user_media_dir):
        shutil.rmtree(user_media_dir)

    return DeleteUserResponse(
        status="success", message="Account and all data deleted successfully"
    )


@router.post(
    "/register-with-import", response_model=RegisterWithImportResponse, status_code=201
)
async def register_with_import(
    hashkey: str = Form(...),
    file: UploadFile = File(...),
):
    """Recreate a user from encrypted dump and import all data."""
    # Read dump file
    content = await file.read()

    # Extract unencrypted meta to get the source username for key derivation
    meta = read_dump_meta(content)
    if meta is None:
        raise HTTPException(
            400,
            "Unrecognised dump format. This may be a legacy dump created before version 1.0.",
        )

    source_username = meta.get("username")
    if not source_username:
        raise HTTPException(400, "Dump meta is missing username.")

    fernet_key = derive_dump_key(hashkey, source_username)
    data = read_encrypted_dump(content, fernet_key)

    if data is None:
        raise HTTPException(
            400, "Failed to decrypt dump. Invalid hashkey or corrupted file."
        )

    valid, msg = validate_dump_structure(data)
    if not valid:
        raise HTTPException(400, f"Invalid dump structure: {msg}")

    try:
        data = UserDataDump.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(400, f"Invalid dump structure: {exc.error_count()} errors")

    dump_username = data.user.username
    dump_password_hash = data.user.password_hash
    dump_hashkey_hash = data.user.hashkey_hash

    if not dump_username or not isinstance(dump_username, str):
        raise HTTPException(
            400,
            "Dump does not contain username. Re-export data with a newer version.",
        )

    if not dump_password_hash or not isinstance(dump_password_hash, str):
        raise HTTPException(
            400,
            "Dump does not contain password hash. Re-export data with a newer version.",
        )

    existing = get_user_by_username(dump_username)
    if existing:
        raise HTTPException(status_code=409, detail="Username from dump already exists")

    # Create user
    user = UserModel(
        username=dump_username,
        password_hash=dump_password_hash,
        hashkey_hash=dump_hashkey_hash,
        dump_key=data.user.dump_key,
        theme=data.user.theme,
        created_at=data.user.created_at,
    )
    user_id = create_user(user)

    # Import the data using the shared utility
    import_result = await import_dump_data(data, dump_username)

    record_user_login(user_id)
    token = create_access_token(user_id, dump_username)

    return RegisterWithImportResponse(
        username=dump_username,
        access_token=token,
        import_result=ImportResult(
            status=import_result.status,
            workspaces_imported=import_result.workspaces_imported,
            journals_imported=import_result.journals_imported,
            entries_imported=import_result.entries_imported,
            tags_imported=import_result.tags_imported,
            skipped=import_result.skipped,
        ),
    )
