from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from user_model import apply_seed_defaults, merge_user_model, seed_memories, seed_user_model


WORD_RE = re.compile(r"[\w\u0590-\u05ff]{2,}", re.UNICODE)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def tokenize(text: str) -> set[str]:
    return {match.group(0).casefold() for match in WORD_RE.finditer(text or "")}


@dataclass
class MemoryRecord:
    id: int
    category: str
    content: str
    confidence: float
    importance: float
    key: str | None
    created_at: str
    updated_at: str
    metadata: dict[str, Any]


class SQLiteMemoryStore:
    def __init__(self, database_path: Path, primary_user_id: str):
        self.database_path = Path(database_path)
        self.primary_user_id = primary_user_id
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.database_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._initialize()
        self._seed_primary_user()

    def ensure_user(self, user_id: str, display_name: str | None = None) -> dict[str, Any]:
        with self._lock:
            existing = self.get_user_model(user_id)
            if existing is not None:
                return existing
            profile = seed_user_model(display_name=display_name)
            now = utcnow_iso()
            self._conn.execute(
                """
                INSERT INTO users (user_id, profile_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, json.dumps(profile, ensure_ascii=False), now, now),
            )
            self._conn.commit()
            return profile

    def get_user_model(self, user_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT profile_json FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        return json.loads(row["profile_json"])

    def update_user_model(self, user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            current = self.get_user_model(user_id) or seed_user_model()
            merged = merge_user_model(current, updates)
            now = utcnow_iso()
            self._conn.execute(
                """
                INSERT INTO users (user_id, profile_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    profile_json = excluded.profile_json,
                    updated_at = excluded.updated_at
                """,
                (user_id, json.dumps(merged, ensure_ascii=False), now, now),
            )
            self._conn.commit()
            return merged

    def save_memory(
        self,
        user_id: str,
        category: str,
        content: str,
        *,
        key: str | None = None,
        confidence: float = 0.5,
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        normalized = self._memory_fingerprint(user_id=user_id, category=category, key=key, content=content)
        now = utcnow_iso()
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)

        with self._lock:
            existing = self._conn.execute(
                "SELECT id, confidence, importance, metadata_json FROM memories WHERE fingerprint = ?",
                (normalized,),
            ).fetchone()
            if existing:
                merged_metadata = self._merge_metadata(existing["metadata_json"], metadata_json)
                self._conn.execute(
                    """
                    UPDATE memories
                    SET confidence = ?, importance = ?, metadata_json = ?, updated_at = ?, last_seen_at = ?
                    WHERE id = ?
                    """,
                    (
                        max(float(existing["confidence"]), confidence),
                        max(float(existing["importance"]), importance),
                        merged_metadata,
                        now,
                        now,
                        existing["id"],
                    ),
                )
                self._conn.commit()
                return int(existing["id"])

            cursor = self._conn.execute(
                """
                INSERT INTO memories (
                    user_id, category, key, content, confidence, importance,
                    metadata_json, fingerprint, created_at, updated_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    category,
                    key,
                    content.strip(),
                    confidence,
                    importance,
                    metadata_json,
                    normalized,
                    now,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return int(cursor.lastrowid)

    def retrieve_relevant_memories(
        self,
        user_id: str,
        query: str,
        *,
        limit: int = 8,
        categories: list[str] | None = None,
        scan_limit: int = 250,
    ) -> list[MemoryRecord]:
        sql = """
            SELECT *
            FROM memories
            WHERE user_id = ?
        """
        params: list[Any] = [user_id]
        if categories:
            placeholders = ", ".join("?" for _ in categories)
            sql += f" AND category IN ({placeholders})"
            params.extend(categories)
        sql += " ORDER BY importance DESC, confidence DESC, updated_at DESC LIMIT ?"
        params.append(scan_limit)
        rows = self._conn.execute(sql, params).fetchall()
        query_tokens = tokenize(query)
        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            content_tokens = tokenize(row["content"])
            overlap = len(query_tokens & content_tokens)
            exact_bonus = 1.0 if query and query.casefold() in row["content"].casefold() else 0.0
            score = (
                float(row["importance"]) * 2.0
                + float(row["confidence"]) * 1.5
                + overlap * 1.25
                + exact_bonus
            )
            scored.append((score, row))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [self._row_to_memory(row) for _, row in scored[:limit] if _ > 0]

    def search_memory(self, user_id: str, query: str, *, limit: int = 8) -> list[MemoryRecord]:
        pattern = f"%{query.strip()}%"
        rows = self._conn.execute(
            """
            SELECT *
            FROM memories
            WHERE user_id = ? AND content LIKE ?
            ORDER BY importance DESC, confidence DESC, updated_at DESC
            LIMIT ?
            """,
            (user_id, pattern, limit),
        ).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def log_conversation(
        self,
        user_id: str,
        role: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        now = utcnow_iso()
        cursor = self._conn.execute(
            """
            INSERT INTO conversations (user_id, role, content, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, role, content.strip(), json.dumps(metadata or {}, ensure_ascii=False), now),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def get_recent_conversation(self, user_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT role, content, metadata_json, created_at
            FROM conversations
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        result = []
        for row in reversed(rows):
            result.append(
                {
                    "role": row["role"],
                    "content": row["content"],
                    "metadata": json.loads(row["metadata_json"] or "{}"),
                    "created_at": row["created_at"],
                }
            )
        return result

    def _initialize(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;

                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    profile_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    key TEXT,
                    content TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    importance REAL NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_memories_user_updated
                ON memories (user_id, updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_memories_user_category
                ON memories (user_id, category);

                CREATE INDEX IF NOT EXISTS idx_conversations_user_id
                ON conversations (user_id, id DESC);
                """
            )
            self._conn.commit()

    def _seed_primary_user(self) -> None:
        with self._lock:
            current = self.get_user_model(self.primary_user_id)
            seeded_profile = seed_user_model()
            now = utcnow_iso()

            if current is None:
                profile_to_store = seeded_profile
                created_at = now
            else:
                profile_to_store = apply_seed_defaults(current, seeded_profile)
                created_at = self._conn.execute(
                    "SELECT created_at FROM users WHERE user_id = ?",
                    (self.primary_user_id,),
                ).fetchone()
                created_at = created_at["created_at"] if created_at else now

            self._conn.execute(
                """
                INSERT INTO users (user_id, profile_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    profile_json = excluded.profile_json,
                    updated_at = excluded.updated_at
                """,
                (self.primary_user_id, json.dumps(profile_to_store, ensure_ascii=False), created_at, now),
            )

            for memory in seed_memories():
                self.save_memory(
                    self.primary_user_id,
                    memory["category"],
                    memory["content"],
                    key=memory.get("key"),
                    confidence=memory["confidence"],
                    importance=memory["importance"],
                    metadata={"seeded": True, "seed_version": profile_to_store.get("profile_seed_id")},
                )
            self._conn.commit()

    def _row_to_memory(self, row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=int(row["id"]),
            category=row["category"],
            content=row["content"],
            confidence=float(row["confidence"]),
            importance=float(row["importance"]),
            key=row["key"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    @staticmethod
    def _memory_fingerprint(user_id: str, category: str, key: str | None, content: str) -> str:
        payload = f"{user_id}|{category}|{(key or '').strip().casefold()}|{content.strip().casefold()}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _merge_metadata(existing_json: str, new_json: str) -> str:
        existing = json.loads(existing_json or "{}")
        incoming = json.loads(new_json or "{}")
        merged = {**existing, **incoming}
        return json.dumps(merged, ensure_ascii=False)
