from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os

router = APIRouter()

USERNAME = os.getenv("AUTH_USERNAME") or os.getenv("OPERATOR_USERNAME") or "admin"
PASSWORD = os.getenv("AUTH_PASSWORD") or os.getenv("OPERATOR_PASSWORD") or "admin"


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(data: LoginRequest):
    if data.username == USERNAME and data.password == PASSWORD:
        return {
            "success": True,
            "message": "Authenticated",
            "username": USERNAME,
            "access_token": "kua-local-session-token",
            "token_type": "bearer"
        }

    raise HTTPException(
        status_code=401,
        detail="Invalid username or password"
    )


@router.get("/me")
def me():
    return {
        "success": True,
        "username": USERNAME
    }


@router.post("/logout")
def logout():
    return {
        "success": True,
        "message": "Logged out"
    }