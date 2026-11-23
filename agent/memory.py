"""Session memory interface and thread-safe in-process implementation."""

import logging
from datetime import datetime, timezone
from threading import RLock
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from data.schemas import SavedSearch, UserPreferences

logger = logging.getLogger(__name__)


class ConversationMessage(BaseModel):
    """A user, assistant, or tool-output entry retained in session memory."""

    role: Literal["user", "assistant", "tool"]
    content: str
    tool_name: str | None = None


class SessionState(BaseModel):
    """Snapshot of the state needed to plan a turn."""

    preferences: UserPreferences = Field(default_factory=UserPreferences)
    saved_searches: list[SavedSearch] = Field(default_factory=list)
    message_history: list[ConversationMessage] = Field(default_factory=list)


class MemoryStore(Protocol):
    """Storage contract that can be implemented by in-memory or remote stores."""

    def get_state(self, session_id: str) -> SessionState:
        """Return a detached snapshot of one session."""

    def update_preferences(
        self, session_id: str, preferences: UserPreferences
    ) -> None:
        """Replace a session's current preferences."""

    def save_search(
        self, session_id: str, filters: UserPreferences
    ) -> SavedSearch:
        """Persist a saved search in a session."""

    def get_searches(self, session_id: str) -> list[SavedSearch]:
        """Return saved searches for one session."""

    def add_message(
        self,
        session_id: str,
        role: Literal["user", "assistant", "tool"],
        content: str,
        tool_name: str | None = None,
    ) -> None:
        """Append a user or assistant message to the session history."""


class SessionMemory:
    """Thread-safe in-process implementation of the session memory contract."""

    def __init__(self) -> None:
        self._preferences: dict[str, UserPreferences] = {}
        self._searches: dict[str, list[SavedSearch]] = {}
        self._history: dict[str, list[ConversationMessage]] = {}
        self._lock = RLock()

    def get_state(self, session_id: str) -> SessionState:
        """Return preferences, searches, and history as detached model copies."""
        with self._lock:
            return SessionState(
                preferences=self._preferences.get(
                    session_id, UserPreferences()
                ).model_copy(deep=True),
                saved_searches=[
                    search.model_copy(deep=True)
                    for search in self._searches.get(session_id, [])
                ],
                message_history=[
                    message.model_copy(deep=True)
                    for message in self._history.get(session_id, [])
                ],
            )

    def update_preferences(
        self, session_id: str, preferences: UserPreferences
    ) -> None:
        """Replace preferences for a session."""
        if not session_id.strip():
            raise ValueError("session_id must not be empty")
        with self._lock:
            self._preferences[session_id] = preferences.model_copy(deep=True)
        logger.info("Updated session preferences", extra={"session_id": session_id})

    def save_search(
        self, session_id: str, filters: UserPreferences
    ) -> SavedSearch:
        """Store a copy of filters and return the timestamped saved search."""
        if not session_id.strip():
            raise ValueError("session_id must not be empty")
        saved = SavedSearch(
            id=str(uuid4()),
            session_id=session_id,
            filters=filters.model_copy(deep=True),
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._searches.setdefault(session_id, []).append(saved)
        logger.info(
            "Stored search in session memory",
            extra={"session_id": session_id, "search_id": saved.id},
        )
        return saved

    def get_searches(self, session_id: str) -> list[SavedSearch]:
        """Return saved searches for one session in insertion order."""
        with self._lock:
            return [
                search.model_copy(deep=True)
                for search in self._searches.get(session_id, [])
            ]

    def add_message(
        self,
        session_id: str,
        role: Literal["user", "assistant", "tool"],
        content: str,
        tool_name: str | None = None,
    ) -> None:
        """Append a message without logging its potentially sensitive content."""
        if not session_id.strip():
            raise ValueError("session_id must not be empty")
        with self._lock:
            self._history.setdefault(session_id, []).append(
                ConversationMessage(role=role, content=content, tool_name=tool_name)
            )
        logger.info(
            "Stored conversation message",
            extra={"session_id": session_id, "role": role, "tool_name": tool_name},
        )
