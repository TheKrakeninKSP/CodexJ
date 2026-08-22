from datetime import datetime

from pydantic import BaseModel

from backend.type_defs import id_type


class JWT_Payload(BaseModel):
    user_id: id_type
    username: str
    expire: datetime
