"""
Chat session endpoints — CRUD for persistent conversations.

These endpoints replace the frontend's previous localStorage-only model.
The frontend still caches sessions client-side for snappy UX, but the
server is now the source of truth: clearing localStorage no longer loses
history, and a user could in principle sign in on another device and see
their conversations.

Endpoint map
------------
  POST   /api/v1/chat/sessions                 → create session
  GET    /api/v1/chat/sessions                 → list sessions (metadata only)
  GET    /api/v1/chat/sessions/{id}            → session detail + messages
  PATCH  /api/v1/chat/sessions/{id}            → rename or update system prompt
  DELETE /api/v1/chat/sessions/{id}            → delete session (cascades messages)
  POST   /api/v1/chat/sessions/{id}/messages   → append a message

Auth
----
There is no real authentication yet. All operations attribute to a seeded
`DEFAULT_USER_ID` until Part III. The repository layer keeps user-scoping in
place so swapping to a real `get_current_user` dependency is a one-line
change.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway.app.services.chat_repository import ChatRepository
from shared.db import get_session
from shared.schemas import (
    ChatMessageCreate,
    ChatMessageOut,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionOut,
    ChatSessionUpdate,
)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


def _parse_uuid(raw: str) -> uuid.UUID:
    """Strict UUID parsing — returns a 400 (not 500) on malformed input."""
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid session id") from exc


def _repo(db: AsyncSession = Depends(get_session)) -> ChatRepository:
    """Build a per-request repository bound to the default user.

    Swap this for an auth-aware dependency in Part III to get real
    per-user session scoping.
    """
    return ChatRepository(db)


@router.post("/sessions", response_model=ChatSessionOut, status_code=201)
async def create_session(
    payload: ChatSessionCreate,
    repo: ChatRepository = Depends(_repo),
) -> ChatSessionOut:
    return await repo.create_session(payload)


@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_sessions(
    repo: ChatRepository = Depends(_repo),
) -> list[ChatSessionOut]:
    return list(await repo.list_sessions())


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
async def get_session(
    session_id: str,
    repo: ChatRepository = Depends(_repo),
) -> ChatSessionDetail:
    detail = await repo.get_session_detail(_parse_uuid(session_id))
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return detail


@router.patch("/sessions/{session_id}", response_model=ChatSessionOut)
async def update_session(
    session_id: str,
    payload: ChatSessionUpdate,
    repo: ChatRepository = Depends(_repo),
) -> ChatSessionOut:
    updated = await repo.update_session(_parse_uuid(session_id), payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return updated


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    repo: ChatRepository = Depends(_repo),
) -> None:
    deleted = await repo.delete_session(_parse_uuid(session_id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatMessageOut,
    status_code=201,
)
async def append_message(
    session_id: str,
    payload: ChatMessageCreate,
    repo: ChatRepository = Depends(_repo),
) -> ChatMessageOut:
    msg = await repo.append_message(_parse_uuid(session_id), payload)
    if msg is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return msg
