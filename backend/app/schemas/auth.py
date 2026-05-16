"""Pydantic schemas — auth."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserPublic(BaseModel):
    id: UUID
    username: str
    display_name: str
    clearance: str
    is_active: bool

    model_config = {"from_attributes": True}


class SessionInfo(BaseModel):
    session_id: str
    user: UserPublic
    issued_at: datetime
