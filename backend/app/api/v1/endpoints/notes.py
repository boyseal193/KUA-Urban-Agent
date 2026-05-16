"""Per-deal acquisition notes."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser
from app.db.session import get_db
from app.repositories.note_repository import create_note, list_notes_for_property
from app.schemas.property import NoteCreate, NoteOut

router = APIRouter(tags=["notes"])


@router.get("/properties/{property_id}/notes", response_model=list[NoteOut])
async def list_notes(
    property_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    rows = await list_notes_for_property(db, property_id)
    return [NoteOut.model_validate(n) for n in rows]


@router.post("/properties/{property_id}/notes", response_model=NoteOut)
async def add_note(
    property_id: UUID,
    body: NoteCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    n = await create_note(db, property_id=property_id, user_id=user.id, body=body.body)
    return NoteOut.model_validate(n)
