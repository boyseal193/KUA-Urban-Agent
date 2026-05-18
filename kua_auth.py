from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os

router = APIRouter()

USERNAME = os.getenv("AUTH_USERNAME", "admin")
PASSWORD = os.getenv("AUTH_PASSWORD", "admin")


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
            "access_token": "kua-session-token",
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
        "success": True
    }