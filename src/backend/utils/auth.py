import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.database.querying import get_user_by_username
from backend.database.structural import UserModel
from backend.globalvar import IS_SESSION_PRIVILEGED
from backend.models.auth import JWT_Payload
from backend.types import id_type
from backend.utils.addressing import is_dev_env
from backend.utils.common import to_dict

# Use embedded config when running as frozen executable
if is_dev_env():
    SECRET_KEY = os.getenv("JWT_SECRET")
    ALGORITHM = os.getenv("JWT_ALGORITHM")
    EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "7"))
else:
    try:
        from build_config import (  # type: ignore[import-not-found]
            JWT_ALGORITHM,
            JWT_EXPIRE_DAYS,
            JWT_SECRET,
        )

        SECRET_KEY = JWT_SECRET
        ALGORITHM = JWT_ALGORITHM
        EXPIRE_DAYS = JWT_EXPIRE_DAYS
    except ImportError as exc:
        # Throw an error and exit the program if build_config is not found in production
        raise RuntimeError(
            "build_config not found. Ensure the build_config module is present."
        ) from exc

if not SECRET_KEY or not ALGORITHM or not EXPIRE_DAYS:
    raise RuntimeError(
        "JWT configuration is missing. Ensure JWT_SECRET, JWT_ALGORITHM, and JWT_EXPIRE_DAYS are set."
    )
secret_key: str = SECRET_KEY
algorithm: str = ALGORITHM
expire_days: int = EXPIRE_DAYS

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
bearer_scheme = HTTPBearer()


# ── Password / hashkey helpers ────────────────────────────────────────────────


def hash_secret(secret: str) -> str:
    return pwd_context.hash(secret)


def verify_secret(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT helpers ───────────────────────────────────────────────────────────────


def create_access_token(
    user_id: id_type,
    username: str,
    *,
    is_privileged: bool = False,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=expire_days)
    payload = JWT_Payload(user_id=user_id, username=username, expire=expire)
    payload = to_dict(payload)
    if payload is None:
        return ""
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def decode_token(token: str) -> JWT_Payload:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        payload_obj = JWT_Payload(
            user_id=payload.get("user_id"),
            username=payload.get("username"),
            expire=payload.get("expire"),
        )
        return payload_obj
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


# ── FastAPI dependency ────────────────────────────────────────────────────────


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> UserModel:
    payload = decode_token(credentials.credentials)
    username = payload.username
    user = get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def set_privileged_mode(is_privileged: bool):
    global IS_SESSION_PRIVILEGED
    IS_SESSION_PRIVILEGED = is_privileged


async def require_privileged_mode():
    global IS_SESSION_PRIVILEGED
    if not IS_SESSION_PRIVILEGED:
        raise HTTPException(status_code=403, detail="Privileged mode required")
