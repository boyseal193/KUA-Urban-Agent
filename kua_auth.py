from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
import json
import secrets
import time

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


def get_users():
    raw_users = os.getenv("AUTH_USERS")

    if raw_users:
        try:
            users = json.loads(raw_users)
            if isinstance(users, list):
                return users
        except Exception:
            pass

    return [
        {
            "username": os.getenv("AUTH_USERNAME", "admin"),
            "password": os.getenv("AUTH_PASSWORD", "admin"),
        }
    ]


def make_token(username: str):
    random_part = secrets.token_hex(16)
    timestamp = int(time.time())
    return f"kua-{username}-{timestamp}-{random_part}"


@router.post("/login")
def login(data: LoginRequest):
    users = get_users()

    for user in users:
        username = user.get("username")
        password = user.get("password")

        if data.username == username and data.password == password:
            return {
                "success": True,
                "message": "Authenticated",
                "username": username,
                "access_token": make_token(username),
                "token_type": "bearer",
            }

    raise HTTPException(
        status_code=401,
        detail="Invalid username or password"
    )


@router.get("/me")
def me():
    return {
        "success": True,
        "message": "Authenticated"
    }


@router.post("/logout")
def logout():
    return {
        "success": True,
        "message": "Logged out"
    }