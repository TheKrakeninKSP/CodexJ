import os
import secrets
import shutil
from datetime import datetime, timezone
from typing import Any

from app.constants import MEDIA_PATH
from app.database import get_db
from app.models.user import DEFAULT_THEME, ThemeName, UserCreate, normalize_theme
from app.utils.auth import (create_access_token, get_current_user, hash_secret,
                            require_privileged_mode, verify_secret)
from app.utils.data_management import (decode_and_save_media,
                                       read_encrypted_dump,
                                       update_media_refs_in_body,
                                       validate_dump_structure)
from app.utils.entry_utils import extract_media_refs
from bson import ObjectId
from fastapi import (APIRouter, Depends, File, Form, HTTPException, UploadFile,
                     status)
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class UnlockRequest(BaseModel):
    username: str
    hashkey: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PrivilegedModeRequest(BaseModel):
    password: str


class RegisterResponse(BaseModel):
    username: str
    access_token: str
    token_type: str = "bearer"
    hashkey: str  # shown only once for user to save


class DeleteUserResponse(BaseModel):
    status: str
    message: str


class UserPreferencesResponse(BaseModel):
    theme: ThemeName = DEFAULT_THEME


class UpdateUserPreferencesRequest(BaseModel):
    theme: ThemeName


class ImportResult(BaseModel):
    status: str
    workspaces_imported: int = 0
    journals_imported: int = 0
    entries_imported: int = 0
    entry_types_imported: int = 0
    skipped: int = 0


class RegisterWithImportResponse(BaseModel):
    username: str
    access_token: str
    token_type: str = "bearer"
    import_result: ImportResult


def _build_user_lookup(current_user: dict[str, Any]) -> dict[str, Any]:
    user_id = current_user.get("id")
    if isinstance(user_id, str) and ObjectId.is_valid(user_id):
        return {"_id": ObjectId(user_id)}
    return {"username": current_user["username"]}


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(payload: UserCreate, db=Depends(get_db)):
    existing = await db["users"].find_one({"username": payload.username})
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")

    # Generate a one-time hashkey (32 random bytes → 64-char hex string)
    plaintext_hashkey = secrets.token_hex(32)

    user_doc = {
        "username": payload.username,
        "password_hash": hash_secret(payload.password),
        "hashkey_hash": hash_secret(plaintext_hashkey),
        "theme": DEFAULT_THEME,
    }
    result = await db["users"].insert_one(user_doc)
    user_id = str(result.inserted_id)

    # Create a default workspace for the user
    await db["workspaces"].insert_one({"user_id": user_id, "name": "Workspace A"})

    token = create_access_token(user_id, payload.username)
    return RegisterResponse(
        username=payload.username,
        access_token=token,
        hashkey=plaintext_hashkey,
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db=Depends(get_db)):
    user = await db["users"].find_one({"username": payload.username})
    if not user or not verify_secret(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = create_access_token(str(user["_id"]), user["username"])
    return TokenResponse(access_token=token)


@router.post("/unlock", response_model=TokenResponse)
async def unlock(payload: UnlockRequest, db=Depends(get_db)):
    user = await db["users"].find_one({"username": payload.username})
    if not user or not verify_secret(payload.hashkey, user["hashkey_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or hashkey",
        )
    token = create_access_token(str(user["_id"]), user["username"])
    return TokenResponse(access_token=token)


@router.post("/privileged", response_model=TokenResponse)
async def enable_privileged_mode(
    payload: PrivilegedModeRequest,
    current_user: dict = Depends(get_current_user),
):
    if not verify_secret(payload.password, current_user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password",
        )
    token = create_access_token(
        current_user["id"],
        current_user["username"],
        is_privileged=True,
    )
    return TokenResponse(access_token=token)


@router.post("/privileged/disable", response_model=TokenResponse)
async def disable_privileged_mode(
    current_user: dict = Depends(get_current_user),
):
    token = create_access_token(current_user["id"], current_user["username"])
    return TokenResponse(access_token=token)


@router.get("/preferences", response_model=UserPreferencesResponse)
async def get_user_preferences(
    current_user: dict = Depends(get_current_user),
):
    return UserPreferencesResponse(theme=normalize_theme(current_user.get("theme")))


@router.patch("/preferences", response_model=UserPreferencesResponse)
async def update_user_preferences(
    payload: UpdateUserPreferencesRequest,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    theme = normalize_theme(payload.theme)
    result = await db["users"].update_one(
        _build_user_lookup(current_user),
        {"$set": {"theme": theme}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return UserPreferencesResponse(theme=theme)


@router.delete("/delete", response_model=DeleteUserResponse)
async def delete_user(
    current_user: dict = Depends(require_privileged_mode),
    db=Depends(get_db),
):
    """Delete user account and all associated data."""
    user_id = current_user["id"]

    # Get all workspace IDs for this user
    ws_ids = [
        str(ws["_id"])
        async for ws in db["workspaces"].find({"user_id": user_id}, {"_id": 1})
    ]

    # Get all journal IDs for those workspaces
    jr_ids = [
        str(jr["_id"])
        async for jr in db["journals"].find(
            {"workspace_id": {"$in": ws_ids}}, {"_id": 1}
        )
    ]

    # Delete all entries in those journals
    await db["entries"].delete_many({"journal_id": {"$in": jr_ids}})

    # Delete all journals
    await db["journals"].delete_many({"workspace_id": {"$in": ws_ids}})

    # Delete all workspaces
    await db["workspaces"].delete_many({"user_id": user_id})

    # Delete all entry types
    await db["entry_types"].delete_many({"user_id": user_id})

    # Delete all media records
    await db["media"].delete_many({"user_id": user_id})

    # Delete user's media directory if it exists
    user_media_dir = os.path.join(MEDIA_PATH, user_id)
    if os.path.exists(user_media_dir):
        shutil.rmtree(user_media_dir)

    # Delete the user
    await db["users"].delete_one({"_id": ObjectId(user_id)})

    return DeleteUserResponse(
        status="success", message="Account and all data deleted successfully"
    )


def _now():
    return datetime.now(timezone.utc)


@router.post(
    "/register-with-import", response_model=RegisterWithImportResponse, status_code=201
)
async def register_with_import(
    encryption_key: str = Form(...),
    file: UploadFile = File(...),
    db=Depends(get_db),
):
    """Recreate a user from encrypted dump and import all data."""
    # Validate inputs
    if len(encryption_key) < 8 or len(encryption_key) > 64:
        raise HTTPException(400, "Encryption key must be 8-64 characters")

    # Read and validate dump first
    content = await file.read()
    data = read_encrypted_dump(content, encryption_key)

    if data is None:
        raise HTTPException(
            400, "Failed to decrypt dump. Invalid key or corrupted file."
        )

    valid, msg = validate_dump_structure(data)
    if not valid:
        raise HTTPException(400, f"Invalid dump structure: {msg}")

    dump_username = data.get("username")
    dump_password_hash = data.get("password_hash")
    dump_hashkey_hash = data.get("hashkey_hash")

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

    existing = await db["users"].find_one({"username": dump_username})
    if existing:
        raise HTTPException(status_code=409, detail="Username from dump already exists")

    # Create user
    user_doc = {
        "username": dump_username,
        "password_hash": dump_password_hash,
        "hashkey_hash": dump_hashkey_hash or hash_secret(secrets.token_hex(32)),
        "theme": normalize_theme(data.get("theme")),
    }
    result = await db["users"].insert_one(user_doc)
    user_id = str(result.inserted_id)

    # Import the data
    import_result = ImportResult(status="success")

    # ID mapping: old_id -> new_id
    ws_id_map = {}
    jr_id_map = {}
    media_url_map = {}

    # Import workspaces
    for ws_data in data.get("workspaces", []):
        doc = {
            "user_id": user_id,
            "name": ws_data["name"],
            "created_at": ws_data.get("created_at", _now()),
        }
        res = await db["workspaces"].insert_one(doc)
        ws_id_map[ws_data["id"]] = str(res.inserted_id)
        import_result.workspaces_imported += 1

    # Import journals
    for jr_data in data.get("journals", []):
        new_ws_id = ws_id_map.get(jr_data["workspace_id"])
        if not new_ws_id:
            import_result.skipped += 1
            continue

        doc = {
            "workspace_id": new_ws_id,
            "name": jr_data["name"],
            "description": jr_data.get("description"),
            "created_at": jr_data.get("created_at", _now()),
        }
        res = await db["journals"].insert_one(doc)
        jr_id_map[jr_data["id"]] = str(res.inserted_id)
        import_result.journals_imported += 1

    # Import media first (to update entry references)
    for media_data in data.get("media", []):
        if not media_data.get("content_base64"):
            continue

        success, stored_filename, new_url = decode_and_save_media(
            user_id,
            media_data["content_base64"],
            media_data["original_filename"],
        )

        if success:
            doc = {
                "user_id": user_id,
                "original_filename": media_data["original_filename"],
                "stored_filename": stored_filename,
                "media_type": media_data["media_type"],
                "file_size": media_data["file_size"],
                "created_at": _now(),
            }
            await db["media"].insert_one(doc)

            old_url = (
                f"http://localhost:8128/media/{data['user_id']}/"
                f"{media_data['stored_filename']}"
            )
            media_url_map[old_url] = new_url

    # Import entries
    for entry_data in data.get("entries", []):
        new_jr_id = jr_id_map.get(entry_data["journal_id"])
        if not new_jr_id:
            import_result.skipped += 1
            continue

        body = entry_data.get("body", {})
        updated_body = update_media_refs_in_body(body, media_url_map)

        new_entry_id = ObjectId()
        doc = {
            "_id": new_entry_id,
            "id": str(new_entry_id),
            "journal_id": new_jr_id,
            "type": entry_data["type"],
            "name": entry_data["name"],
            "body": updated_body,
            "custom_metadata": entry_data.get("custom_metadata", []),
            "media_refs": extract_media_refs(updated_body),
            "date_created": entry_data.get("date_created", _now()),
            "updated_at": _now(),
        }
        await db["entries"].insert_one(doc)
        import_result.entries_imported += 1

    # Import entry types
    for et_data in data.get("entry_types", []):
        existing_et = await db["entry_types"].find_one(
            {"user_id": user_id, "name": et_data["name"]}
        )
        if existing_et:
            import_result.skipped += 1
            continue

        doc = {
            "user_id": user_id,
            "name": et_data["name"],
            "created_at": et_data.get("created_at", _now()),
        }
        await db["entry_types"].insert_one(doc)
        import_result.entry_types_imported += 1

    token = create_access_token(user_id, dump_username)

    return RegisterWithImportResponse(
        username=dump_username,
        access_token=token,
        import_result=import_result,
    )
