from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(..., description="User e-mail")
    password: str = Field(..., min_length=1, description="User password")


class UserOut(BaseModel):
    id: UUID
    email: str
    created_at: datetime


class LoginResponse(BaseModel):
    user: UserOut
