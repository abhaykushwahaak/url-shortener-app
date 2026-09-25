"""Auth request/response models."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr = Field(..., examples=["student@example.com"])
    # bcrypt only consumes the first 72 bytes, and recent versions raise rather
    # than silently truncate - so the limit is enforced at the schema boundary.
    password: str = Field(..., min_length=8, max_length=72, examples=["supersecret1"])


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token lifetime in seconds")


class TokenWithUser(Token):
    user: UserRead