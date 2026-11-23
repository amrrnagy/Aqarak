"""Save user property filters into session memory."""

import logging
from collections.abc import Mapping

from agent.memory import MemoryStore, SessionMemory
from data.schemas import SavedSearch, UserPreferences

_DEFAULT_MEMORY = SessionMemory()
logger = logging.getLogger(__name__)


def save_search(
    session_id: str,
    filters: UserPreferences | Mapping[str, object],
    memory: MemoryStore = _DEFAULT_MEMORY,
) -> SavedSearch:
    """Validate filters and save them in the supplied session memory."""
    if isinstance(filters, UserPreferences):
        preferences = filters
    else:
        values = dict(filters)
        unknown = set(values) - set(UserPreferences.model_fields)
        if unknown:
            raise ValueError(
                f"Unsupported saved-search filters: {', '.join(sorted(unknown))}"
            )
        preferences = UserPreferences.model_validate(values)
    saved = memory.save_search(session_id, preferences)
    logger.info(
        "Saved property search",
        extra={"session_id": session_id, "search_id": saved.id},
    )
    return saved
