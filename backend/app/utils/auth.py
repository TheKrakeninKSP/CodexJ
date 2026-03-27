import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.database import get_db
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

# Use embedded config when running as frozen executable
if getattr(sys, "frozen", False):
    try:
        from build_config import (  # type: ignore[import-not-found]
            JWT_ALGORITHM,
            JWT_EXPIRE_DAYS,
            JWT_SECRET,
        )

        SECRET_KEY = JWT_SECRET
        ALGORITHM = JWT_ALGORITHM
        EXPIRE_DAYS = JWT_EXPIRE_DAYS
    except ImportError:
        # Fallback if build_config not found
        SECRET_KEY = os.getenv("JWT_SECRET", "change_me_please")
        ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
        EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "7"))
else:
    SECRET_KEY = os.getenv("JWT_SECRET", "change_me_please")
    ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "7"))

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
bearer_scheme = HTTPBearer()


# ── Password / hashkey helpers ────────────────────────────────────────────────


def hash_secret(secret: str) -> str:
    return pwd_context.hash(secret)


def verify_secret(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT helpers ───────────────────────────────────────────────────────────────


def create_access_token(
    user_id: str,
    username: str,
    *,
    is_privileged: bool = False,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=EXPIRE_DAYS)
    payload = {"sub": user_id, "username": username, "exp": expire}
    if is_privileged:
        payload["is_privileged"] = True
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


# ── FastAPI dependency ────────────────────────────────────────────────────────


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db=Depends(get_db),
) -> dict:
    payload = decode_token(credentials.credentials)
    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    from bson import ObjectId

    user = await db["users"].find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    user["id"] = str(user["_id"])
    user["is_privileged"] = bool(payload.get("is_privileged", False))
    return user


async def require_privileged_mode(
    current_user: dict = Depends(get_current_user),
) -> dict:
    if not current_user.get("is_privileged", False):
        raise HTTPException(status_code=403, detail="Privileged mode required")
    return current_user
