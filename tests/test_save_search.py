"""Tests for session-scoped saved search filters."""

import pytest

from agent.memory import SessionMemory
from agent.tools.save_search import save_search
from data.schemas import UserPreferences


def test_saved_search_filters_are_isolated_by_session() -> None:
    memory = SessionMemory()
    saved = save_search(
        "session-a",
        {"budget_max": 5_000_000, "areas": ["New Cairo"]},
        memory,
    )

    assert saved.filters.budget_max == 5_000_000
    assert memory.get_searches("session-a")[0].id == saved.id
    assert memory.get_searches("session-b") == []


def test_unknown_saved_search_filters_are_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported saved-search filters"):
        save_search("session-a", {"unknown_filter": "value"}, SessionMemory())


def test_session_memory_stores_preferences_and_message_history() -> None:
    memory = SessionMemory()
    memory.update_preferences(
        "session-a",
        UserPreferences(budget_max=4_000_000, areas=["New Cairo"]),
    )
    memory.add_message("session-a", "user", "Find a two-bedroom apartment.")
    memory.add_message("session-a", "tool", '{"id":"NC-001"}', tool_name="search")

    state = memory.get_state("session-a")
    assert state.preferences.budget_max == 4_000_000
    assert [message.role for message in state.message_history] == ["user", "tool"]
    assert memory.get_state("session-b").message_history == []
