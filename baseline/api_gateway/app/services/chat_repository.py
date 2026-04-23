"""
Chat repository — CRUD over chat_sessions and chat_messages.

Responsibilities:
    - Create / list / fetch / rename / delete sessions
    - Append messages to a session (and bump session.updated_at)
    - Convert ORM rows to the public Pydantic schemas in shared/schemas.py

Why a repository object (vs. ad-hoc queries in routes):
    Route handlers should describe HTTP behaviour, not SQL. Keeping DB
    queries behind named methods makes them testable in isolation
    (instantiate with an in-memory SQLite session in tests) and lets us
    swap the storage layer later without touching routes.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from shared.models import ChatMessage, ChatSession
from shared.schemas import (
    ChatMessageCreate,
    ChatMessageOut,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionOut,
    ChatSessionUpdate,
)

# Baseline seed user — created by the initial migration. Replaced by a real
# authenticated user id once Part III (security) lands.
DEFAULT_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _message_to_out(m: ChatMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=str(m.id),
        session_id=str(m.session_id),
        role=m.role,
        content=m.content,
        meta=m.meta,
        created_at=m.created_at,
    )


def _session_to_out(s: ChatSession, message_count: int = 0) -> ChatSessionOut:
    return ChatSessionOut(
        id=str(s.id),
        user_id=str(s.user_id),
        title=s.title,
        system_prompt=s.system_prompt,
        created_at=s.created_at,
        updated_at=s.updated_at,
        message_count=message_count,
    )


class ChatRepository:
    """Data-access layer for chat sessions and their messages."""

    def __init__(self, session: AsyncSession, user_id: uuid.UUID = DEFAULT_USER_ID):
        self.session = session
        self.user_id = user_id

    # --- sessions --------------------------------------------------------

    async def create_session(self, payload: ChatSessionCreate) -> ChatSessionOut:
        row = ChatSession(
            user_id=self.user_id,
            title=payload.title or "New Chat",
            system_prompt=payload.system_prompt,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return _session_to_out(row, message_count=0)

    async def list_sessions(self, limit: int = 100) -> Sequence[ChatSessionOut]:
        """List sessions for the current user, most recently updated first.

        Joins `count(messages)` via a subquery so the UI can show
        per-session message counts without a second round trip.
        """
        msg_count = (
            select(ChatMessage.session_id, func.count(ChatMessage.id).label("n"))
            .group_by(ChatMessage.session_id)
            .subquery()
        )
        stmt = (
            select(ChatSession, func.coalesce(msg_count.c.n, 0))
            .outerjoin(msg_count, msg_count.c.session_id == ChatSession.id)
            .where(ChatSession.user_id == self.user_id)
            .order_by(ChatSession.updated_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [_session_to_out(s, count) for s, count in result.all()]

    async def get_session_detail(self, session_id: uuid.UUID) -> ChatSessionDetail | None:
        """Fetch a session plus its messages, ordered chronologically."""
        stmt = (
            select(ChatSession)
            .where(ChatSession.id == session_id, ChatSession.user_id == self.user_id)
            .options(selectinload(ChatSession.messages))
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return ChatSessionDetail(
            **_session_to_out(row, message_count=len(row.messages)).model_dump(),
            messages=[_message_to_out(m) for m in row.messages],
        )

    async def update_session(
        self, session_id: uuid.UUID, payload: ChatSessionUpdate
    ) -> ChatSessionOut | None:
        row = await self.session.get(ChatSession, session_id)
        if row is None or row.user_id != self.user_id:
            return None
        if payload.title is not None:
            row.title = payload.title
        if payload.system_prompt is not None:
            row.system_prompt = payload.system_prompt
        await self.session.commit()
        await self.session.refresh(row)
        return _session_to_out(row)

    async def delete_session(self, session_id: uuid.UUID) -> bool:
        row = await self.session.get(ChatSession, session_id)
        if row is None or row.user_id != self.user_id:
            return False
        await self.session.execute(delete(ChatSession).where(ChatSession.id == session_id))
        await self.session.commit()
        return True

    # --- messages --------------------------------------------------------

    async def append_message(
        self, session_id: uuid.UUID, payload: ChatMessageCreate
    ) -> ChatMessageOut | None:
        """Append a message and touch session.updated_at in one transaction.

        Returns None if the session doesn't exist or isn't owned by the user.
        """
        session_row = await self.session.get(ChatSession, session_id)
        if session_row is None or session_row.user_id != self.user_id:
            return None

        msg = ChatMessage(
            session_id=session_id,
            role=payload.role.value,
            content=payload.content,
            meta=payload.meta,
        )
        self.session.add(msg)
        # Touch updated_at so list ordering reflects activity, not creation.
        session_row.updated_at = func.now()
        await self.session.commit()
        await self.session.refresh(msg)
        return _message_to_out(msg)
