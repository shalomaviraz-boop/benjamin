"""Personal Memory + Profile store. SQLite backend."""
import json
import os
import sqlite3
import time

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "benjamin_memory.db")
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(_DB_PATH)
        _conn.row_factory = sqlite3.Row
        _init_schema(_conn)
    return _conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_profile (
            user_id TEXT PRIMARY KEY,
            profile_json TEXT NOT NULL DEFAULT '{}',
            updated_at REAL
        );
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            type TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at REAL,
            updated_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);
        CREATE INDEX IF NOT EXISTS idx_memories_key_value ON memories(key, value);
        CREATE TABLE IF NOT EXISTS project_state (
            user_id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL DEFAULT '{}',
            updated_at REAL
        );
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# User Profile
# ---------------------------------------------------------------------------

def get_profile(user_id: str) -> dict:
    """Get user profile. Returns empty dict if none."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT profile_json FROM user_profile WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row["profile_json"])
    except json.JSONDecodeError:
        return {}


def upsert_profile(user_id: str, profile: dict) -> None:
    """Insert or update user profile."""
    conn = _get_conn()
    now = time.time()
    conn.execute(
        """INSERT INTO user_profile (user_id, profile_json, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
             profile_json = excluded.profile_json,
             updated_at = excluded.updated_at""",
        (user_id, json.dumps(profile, ensure_ascii=False), now),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Memories
# ---------------------------------------------------------------------------

def add_memory(user_id: str, type: str, key: str, value: str) -> int:
    """Add a memory. Returns row id."""
    conn = _get_conn()
    now = time.time()
    cur = conn.execute(
        """INSERT INTO memories (user_id, type, key, value, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, type, key, value, now, now),
    )
    conn.commit()
    return cur.lastrowid or 0


def search_memories(user_id: str, query: str, limit: int = 8) -> list[dict]:
    """Simple keyword match. Returns list of {id, type, key, value, created_at}."""
    conn = _get_conn()
    words = [w.strip() for w in query.split() if len(w.strip()) > 1]
    if not words:
        rows = conn.execute(
            """SELECT id, type, key, value, created_at FROM memories
               WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    else:
        placeholders = " OR ".join(
            "(key LIKE ? OR value LIKE ?)" for _ in words
        )
        params = [user_id]
        for w in words:
            params.extend([f"%{w}%", f"%{w}%"])
        params.append(limit)
        rows = conn.execute(
            f"""SELECT id, type, key, value, created_at FROM memories
                WHERE user_id = ? AND ({placeholders})
                ORDER BY updated_at DESC LIMIT ?""",
            params,
        ).fetchall()
    return [
        {
            "id": r["id"],
            "type": r["type"],
            "key": r["key"],
            "value": r["value"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def get_all_memories(user_id: str, limit: int = 20) -> list[dict]:
    """Get all memories for user, most recent first."""
    return search_memories(user_id, "", limit=limit)


# ---------------------------------------------------------------------------
# Project State
# ---------------------------------------------------------------------------

def get_project_state(user_id: str) -> dict:
    """Get project state. Returns empty dict if none."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT state_json FROM project_state WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row["state_json"])
    except json.JSONDecodeError:
        return {}


def format_memory_for_worker(memory_context: dict | None) -> str:
    """Compressed memory block for worker prompts. Max 12 bullets total."""
    if not memory_context:
        return ""
    bullets = []
    profile = memory_context.get("user_profile") or {}
    if isinstance(profile, dict) and profile:
        s = json.dumps(profile, ensure_ascii=False)[:200]
        bullets.append(f"Profile: {s}")
    memories = memory_context.get("relevant_memories") or []
    for m in memories[:6]:
        if isinstance(m, dict):
            k, v = m.get("key", ""), str(m.get("value", ""))[:60]
            if k or v:
                bullets.append(f"{k}: {v}".strip())
        elif isinstance(m, str) and m.strip():
            bullets.append(m[:80])
    state = memory_context.get("project_state") or {}
    if isinstance(state, dict) and state:
        s = json.dumps(state, ensure_ascii=False)[:150]
        bullets.append(f"Project: {s}")
    bullets = [b for b in bullets[:12] if b]
    if not bullets:
        return ""
    return "User context:\n" + "\n".join(f"- {b}" for b in bullets) + "\n\n"


def upsert_project_state(user_id: str, state: dict) -> None:
    """Insert or update project state."""
    conn = _get_conn()
    now = time.time()
    conn.execute(
        """INSERT INTO project_state (user_id, state_json, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
             state_json = excluded.state_json,
             updated_at = excluded.updated_at""",
        (user_id, json.dumps(state, ensure_ascii=False), now),
    )
    conn.commit()
