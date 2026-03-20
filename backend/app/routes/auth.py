import os
import secrets

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.database import get_db
from app.models.user import UserCreate, UserOut
from app.utils.auth import hash_secret, verify_secret, create_access_token

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


class RegisterResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    hashkey: str  # shown ONCE — user must save this


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
    }
    result = await db["users"].insert_one(user_doc)
    user_id = str(result.inserted_id)

    # Create a default workspace for the user
    await db["workspaces"].insert_one(
        {"user_id": user_id, "name": "Workspace A"}
    )

    token = create_access_token(user_id, payload.username)
    return RegisterResponse(
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
