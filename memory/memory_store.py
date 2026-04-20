from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "benjamin_memory.db"


def _now_ts() -> int:
    return int(time.time())


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            type TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            UNIQUE(user_id, type, key)
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
    return conn


def _deep_merge(base: Any, update: Any):
    if isinstance(base, dict) and isinstance(update, dict):
        merged = dict(base)
        for k, v in update.items():
            if k in merged:
                merged[k] = _deep_merge(merged[k], v)
            else:
                merged[k] = v
        return merged
    if isinstance(base, list) and isinstance(update, list):
        out = []
        for item in base + update:
            if item not in out:
                out.append(item)
        return out
    return update


def get_personal_model(user_id: str) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT model_json FROM personal_model WHERE user_id = ?", (str(user_id),)).fetchone()
        if not row:
            return None
        data = json.loads(row["model_json"])
        return data if isinstance(data, dict) else None
    except Exception:
        return None
    finally:
        conn.close()


def upsert_personal_model(user_id: str, model: dict | str) -> None:
    data = model if isinstance(model, dict) else {"raw": str(model)}
    current = get_personal_model(user_id) or {}
    merged = _deep_merge(current, data)
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO personal_model(user_id, model_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET model_json=excluded.model_json, updated_at=excluded.updated_at
            """,
            (str(user_id), json.dumps(merged, ensure_ascii=False), _now_ts()),
        )
        conn.commit()
    finally:
        conn.close()


def update_personal_model_field(user_id: str, field: str, value: Any) -> None:
    data = get_personal_model(user_id) or {}
    data[str(field)] = value
    upsert_personal_model(user_id, data)


def get_profile(user_id: str) -> dict:
    model = get_personal_model(user_id) or {}
    return {
        "name": model.get("name", ""),
        "communication_style": model.get("communication_style", ""),
        "main_mission": model.get("current_main_mission", ""),
    }


def get_project_state(user_id: str) -> dict:
    model = get_personal_model(user_id) or {}
    return {
        "main_mission": model.get("current_main_mission", ""),
        "active_goals": model.get("active_goals", []),
        "projects": model.get("projects", []),
    }


def upsert_memory(user_id: str, mtype: str, key: str, value: str) -> None:
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
            ON CONFLICT(user_id, type, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (user_id, mtype, key, value, ts, ts),
        )
        conn.commit()
    finally:
        conn.close()


def add_memory(user_id: str, mtype: str, key: str, value: str) -> None:
    upsert_memory(user_id, mtype, key, value)


def list_memories(user_id: str, limit: int = 50) -> list[dict]:
    limit = max(1, min(int(limit or 50), 200))
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT type, key, value, created_at, updated_at FROM memories WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
            (str(user_id), limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def search_memories(user_id: str, query: str, limit: int = 8) -> list[dict]:
    q = (query or "").strip().lower()
    conn = _get_conn()
    try:
        if not q:
            rows = conn.execute(
                "SELECT type, key, value, created_at, updated_at FROM memories WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
                (str(user_id), limit),
            ).fetchall()
            return [dict(r) for r in rows]
        like = f"%{q}%"
        rows = conn.execute(
            """
            SELECT type, key, value, created_at, updated_at
            FROM memories
            WHERE user_id = ? AND (lower(key) LIKE ? OR lower(value) LIKE ? OR lower(type) LIKE ?)
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (str(user_id), like, like, like, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_memories_by_key(user_id: str, key: str) -> int:
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM memories WHERE user_id = ? AND key = ?", (str(user_id), str(key).strip()))
        conn.commit()
        return cur.rowcount or 0
    finally:
        conn.close()
