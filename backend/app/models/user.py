from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, info=None):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        from pydantic_core import core_schema
        return core_schema.no_info_plain_validator_function(cls.validate)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6)


class UserInDB(BaseModel):
    id: Optional[str] = None
    username: str
    password_hash: str
    hashkey_hash: str
    created_at: datetime = Field(default_factory=utcnow)

    model_config = {"arbitrary_types_allowed": True}


class UserOut(BaseModel):
    id: str
    username: str
    created_at: datetime
