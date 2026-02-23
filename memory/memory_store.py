# memory/memory_store.py
import os
import sqlite3
import time
from typing import Any

DB_PATH = os.getenv("BENJAMIN_MEMORY_DB", "benjamin_memory.db")


def _now_ts() -> int:
    return int(time.time())


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(
        DB_PATH,
        timeout=10,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row

    # Better concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _init_db() -> None:
    conn = _get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profile (
                user_id TEXT PRIMARY KEY,
                profile_json TEXT,
                updated_at INTEGER
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                type TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_state (
                user_id TEXT PRIMARY KEY,
                state_json TEXT,
                updated_at INTEGER
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS personal_model (
                user_id TEXT PRIMARY KEY,
                model_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )

        # Prevent duplicates/spam
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_user_type_key
            ON memories(user_id, type, key)
            """
        )

        # Helps LIKE searches
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_memories_user_updated
            ON memories(user_id, updated_at DESC)
            """
        )

        conn.commit()
    finally:
        conn.close()


_init_db()


# ---------- Profile / Project state ----------

def get_profile(user_id: str) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT profile_json FROM user_profile WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if not row or not row["profile_json"]:
            return None
        # stored as text; keep as-is (caller may store JSON str or dict str)
        return {"profile_json": row["profile_json"]}
    finally:
        conn.close()


def upsert_profile(user_id: str, profile: dict | str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO user_profile(user_id, profile_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              profile_json=excluded.profile_json,
              updated_at=excluded.updated_at
            """,
            (user_id, str(profile), _now_ts()),
        )
        conn.commit()
    finally:
        conn.close()


def get_project_state(user_id: str) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT state_json FROM project_state WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if not row or not row["state_json"]:
            return None
        return {"state_json": row["state_json"]}
    finally:
        conn.close()


def upsert_project_state(user_id: str, state: dict | str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO project_state(user_id, state_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              state_json=excluded.state_json,
              updated_at=excluded.updated_at
            """,
            (user_id, str(state), _now_ts()),
        )
        conn.commit()
    finally:
        conn.close()


# ---------- Personal Model ----------


def get_personal_model(user_id: str) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT model_json FROM personal_model WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if not row or not row["model_json"]:
            return None
        return {"model_json": row["model_json"]}
    finally:
        conn.close()


def upsert_personal_model(user_id: str, model: dict | str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO personal_model(user_id, model_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              model_json=excluded.model_json,
              updated_at=excluded.updated_at
            """,
            (user_id, str(model), _now_ts()),
        )
        conn.commit()
    finally:
        conn.close()


def update_personal_model_field(user_id: str, field: str, value: Any) -> None:
    """
    Lightweight field update (expects model_json stored as dict-like string).
    This keeps it simple for MVP.
    """
    existing = get_personal_model(user_id)
    data = {}
    if existing and existing.get("model_json"):
        try:
            data = eval(existing["model_json"])
        except Exception:
            data = {}

    data[str(field)] = value
    upsert_personal_model(user_id, data)


# ---------- Memories ----------

def upsert_memory(user_id: str, mtype: str, key: str, value: str) -> None:
    """
    Upsert by UNIQUE(user_id,type,key).
    Updates value + updated_at if exists; inserts if not.
    """
    user_id = str(user_id).strip()
    mtype = (mtype or "fact").strip()
    key = (key or "").strip()
    value = (value or "").strip()

    if not user_id or not mtype or not key or not value:
        return

    ts = _now_ts()
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO memories(user_id, type, key, value, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, type, key) DO UPDATE SET
              value=excluded.value,
              updated_at=excluded.updated_at
            """,
            (user_id, mtype, key, value, ts, ts),
        )
        conn.commit()
    finally:
        conn.close()


def add_memory(user_id: str, mtype: str, key: str, value: str) -> None:
    """
    Backward-compatible helper.
    Uses upsert to avoid duplicates.
    """
    upsert_memory(user_id, mtype, key, value)


def list_memories(user_id: str, limit: int = 50) -> list[dict]:
    limit = max(1, min(int(limit or 50), 200))
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT type, key, value, created_at, updated_at
            FROM memories
            WHERE user_id=?
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def search_memories(user_id: str, query: str, limit: int = 8) -> list[dict]:
    """
    Searches in key + value using LIKE.
    Returns: type, key, value, created_at, updated_at
    """
    q = (query or "").strip()
    if not q:
        return []

    limit = max(1, min(int(limit or 8), 50))
    like = f"%{q}%"

    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT type, key, value, created_at, updated_at
            FROM memories
            WHERE user_id=?
              AND (key LIKE ? OR value LIKE ?)
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ?
            """,
            (user_id, like, like, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_memories_by_key(user_id: str, key: str) -> int:
    """
    Deletes all memories for user where key matches exactly (across all types).
    Returns deleted count.
    """
    k = (key or "").strip()
    if not k:
        return 0

    conn = _get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM memories WHERE user_id=? AND key=?",
            (user_id, k),
        )
        conn.commit()
        return int(cur.rowcount or 0)
    finally:
        conn.close()


def get_all_memories(user_id: str, limit: int = 50) -> list[dict]:
    """Backward-compatible alias."""
    return list_memories(user_id, limit=limit)


def format_memory_for_worker(memory_context: dict | None) -> str:
    """
    Keep it short: up to ~12 lines for the worker prompt.
    Expects memory_context with: user_profile, relevant_memories, project_state
    """
    if not memory_context:
        return ""

    lines: list[str] = []

    prof = memory_context.get("user_profile")
    if prof:
        lines.append("USER_PROFILE:")
        lines.append(str(prof)[:300])

    mems = memory_context.get("relevant_memories") or []
    if mems:
        lines.append("RELEVANT_MEMORIES:")
        for m in mems[:8]:
            t = m.get("type", "")
            k = m.get("key", "")
            v = str(m.get("value", ""))[:120]
            lines.append(f"- ({t}) {k}: {v}")

    state = memory_context.get("project_state")
    if state:
        lines.append("PROJECT_STATE:")
        lines.append(str(state)[:300])

    # cap
    return "\n".join(lines[:12])