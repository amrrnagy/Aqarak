"""SQLite-backed API latency, cache, area, listing, and token metrics."""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METRICS_PATH = ROOT / "data" / "processed" / "api_metrics.sqlite"


class MonitoringStore:
    """Persist lightweight operational metrics to a local SQLite database."""

    def __init__(self, db_path: Path | str = DEFAULT_METRICS_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS api_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    cache_hit INTEGER
                );
                CREATE TABLE IF NOT EXISTS request_areas (
                    request_id INTEGER NOT NULL,
                    area TEXT NOT NULL,
                    FOREIGN KEY (request_id) REFERENCES api_requests(id)
                );
                CREATE TABLE IF NOT EXISTS listing_views (
                    request_id INTEGER NOT NULL,
                    listing_id TEXT NOT NULL,
                    FOREIGN KEY (request_id) REFERENCES api_requests(id)
                );
                CREATE TABLE IF NOT EXISTS token_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL,
                    completion_tokens INTEGER NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def record_request(
        self,
        *,
        path: str,
        status_code: int,
        latency_ms: float,
        cache_hit: Optional[bool] = None,
        areas: Sequence[str] = (),
        listing_ids: Sequence[str] = (),
    ) -> None:
        """Persist one request and its optional area and listing associations."""
        created_at = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO api_requests
                    (created_at, path, status_code, latency_ms, cache_hit)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    path,
                    status_code,
                    latency_ms,
                    None if cache_hit is None else int(cache_hit),
                ),
            )
            request_id = cursor.lastrowid
            connection.executemany(
                "INSERT INTO request_areas (request_id, area) VALUES (?, ?)",
                [(request_id, area) for area in sorted(set(areas)) if area],
            )
            connection.executemany(
                "INSERT INTO listing_views (request_id, listing_id) VALUES (?, ?)",
                [(request_id, listing_id) for listing_id in sorted(set(listing_ids))],
            )

    def record_token_usage(
        self, prompt_tokens: Optional[int], completion_tokens: Optional[int]
    ) -> None:
        """Persist token counts when the configured LLM provider supplies them."""
        if prompt_tokens is None and completion_tokens is None:
            return
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO token_usage
                    (created_at, prompt_tokens, completion_tokens)
                VALUES (?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    prompt_tokens or 0,
                    completion_tokens or 0,
                ),
            )

    def get_metrics(self) -> dict[str, object]:
        """Return aggregate metrics for the API analytics endpoint."""
        with closing(self._connect()) as connection, connection:
            request_stats = connection.execute(
                """
                SELECT COUNT(*) AS request_count, AVG(latency_ms) AS average_latency_ms
                FROM api_requests
                """
            ).fetchone()
            cache_stats = connection.execute(
                """
                SELECT
                    SUM(CASE WHEN cache_hit = 1 THEN 1 ELSE 0 END) AS cache_hits,
                    SUM(CASE WHEN cache_hit = 0 THEN 1 ELSE 0 END) AS cache_misses,
                    COUNT(cache_hit) AS cache_requests
                FROM api_requests
                """
            ).fetchone()
            area_rows = connection.execute(
                """
                SELECT area, COUNT(*) AS request_count
                FROM request_areas
                GROUP BY area
                ORDER BY request_count DESC, area
                """
            ).fetchall()
            listing_rows = connection.execute(
                """
                SELECT listing_id, COUNT(*) AS views
                FROM listing_views
                GROUP BY listing_id
                ORDER BY views DESC, listing_id
                LIMIT 10
                """
            ).fetchall()
            latency_rows = connection.execute(
                """
                SELECT created_at, latency_ms
                FROM api_requests
                ORDER BY id DESC
                LIMIT 100
                """
            ).fetchall()
            cache_rows = connection.execute(
                """
                SELECT created_at, cache_hit
                FROM api_requests
                WHERE cache_hit IS NOT NULL
                ORDER BY id DESC
                LIMIT 100
                """
            ).fetchall()
            token_stats = connection.execute(
                """
                SELECT
                    COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) AS completion_tokens
                FROM token_usage
                """
            ).fetchone()

        cache_requests = cache_stats["cache_requests"] or 0
        cache_hits = cache_stats["cache_hits"] or 0
        cache_misses = cache_stats["cache_misses"] or 0
        prompt_tokens = token_stats["prompt_tokens"]
        completion_tokens = token_stats["completion_tokens"]
        return {
            "request_count": request_stats["request_count"],
            "average_latency_ms": round(request_stats["average_latency_ms"] or 0, 2),
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "cache_hit_rate": cache_hits / cache_requests if cache_requests else 0.0,
            "area_request_counts": [
                {"area": row["area"], "count": row["request_count"]}
                for row in area_rows
            ],
            "most_viewed_listings": [
                {"listing_id": row["listing_id"], "views": row["views"]}
                for row in listing_rows
            ],
            "latency_series": [
                {"timestamp": row["created_at"], "latency_ms": row["latency_ms"]}
                for row in reversed(latency_rows)
            ],
            "cache_series": [
                {"timestamp": row["created_at"], "hit": bool(row["cache_hit"])}
                for row in reversed(cache_rows)
            ],
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
