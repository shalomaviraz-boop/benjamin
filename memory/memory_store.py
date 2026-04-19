# memory/memory_store.py
import os
import sqlite3
import time
import json
from typing import Any

DB_PATH = os.getenv("BENJAMIN_MEMORY_DB", "benjamin_memory.db")

CORE_USER_PROFILE = {
    "name": "Matan",
    "identity": "Thinks big, wants leverage, rejects mediocrity, and wants to build something real.",
    "assistant_relationship": "Benjamin should act like a sharp personal operator and strategic partner.",
    "default_response_mode": "Short unless depth is needed.",
    "proactive_preference": "Only send truly valuable updates.",
    "failure_conditions": [
        "If Benjamin sounds like a bot",
        "If answers are generic",
        "If responses are long without value",
    ],
}

CORE_PERSONAL_MODEL = {
    "communication_style": "Short, sharp, direct, intelligent. No fluff. No fake politeness. No robotic phrases. Speak like a smart strategic partner.",
    "decision_style": "Prefers truth over softness. Values leverage. Strategic thinking. Hates wasted time.",
    "current_main_mission": "Build Super Agent / premium personal AI assistant.",
    "secondary_missions": [
        "Break through professionally and financially",
        "Use AI as real advantage",
        "Build smart business",
        "Improve status and capabilities",
    ],
    "interests": [
        "AI",
        "Business",
        "Systems",
        "Psychology",
        "Money / markets",
        "Performance",
        "Fitness",
        "Relationships / dynamics",
    ],
    "dislikes": [
        "Generic answers",
        "Wasted motion",
        "Low intelligence tone",
        "Overexplaining",
        "Bureaucracy",
        "Weak thinking",
    ],
    "how_to_help": [
        "Get to the point fast",
        "Find bottlenecks",
        "Suggest leverage moves",
        "Use previous context",
        "Warn when an idea is weak",
        "Think strategically",
    ],
    "decision_patterns": [
        "Truth over softness",
        "Leverage over busywork",
        "Strategic thinking over reactive thinking",
    ],
    "default_response_mode": "Short unless depth is needed.",
    "proactive_preference": "Only send truly valuable updates.",
    "proactive_focus": [
        "Important AI breakthroughs",
        "Important releases from OpenAI, Anthropic, Google, Meta, xAI",
        "Strong business opportunities relevant to current goals",
        "Strategic insights relevant to the Super Agent project",
        "Important market or macro moves relevant to user interests",
        "Personal reminders tied to stated goals",
    ],
}

CORE_PROJECT_STATE = {
    "active_projects": ["Build Super Agent / premium personal AI assistant"],
    "current_main_mission": "Build Super Agent / premium personal AI assistant.",
    "secondary_missions": [
        "Break through professionally and financially",
        "Use AI as real advantage",
        "Build smart business",
        "Improve status and capabilities",
    ],
}

CORE_MEMORY_ITEMS = [
    ("identity", "user_identity", "Thinks big, wants leverage, rejects mediocrity, and wants to build something real."),
    ("preference", "response_style", "Short, sharp, direct, practical. No fluff. No robotic phrasing."),
    ("preference", "tone_preference", "Speak like a smart strategic partner, not a chatbot."),
    ("preference", "proactive_preference", "Only send truly valuable updates."),
    ("project", "main_mission", "Build Super Agent / premium personal AI assistant."),
    ("goal", "secondary_mission_1", "Break through professionally and financially."),
    ("goal", "secondary_mission_2", "Use AI as real advantage."),
    ("goal", "secondary_mission_3", "Build smart business."),
    ("goal", "secondary_mission_4", "Improve status and capabilities."),
    ("preference", "how_to_help", "Get to the point fast, find bottlenecks, and suggest leverage moves."),
    ("dislike", "dislikes", "Generic answers, wasted motion, low intelligence tone, overexplaining, bureaucracy, weak thinking."),
]


def _now_ts() -> int:
    return int(time.time())


def _serialize_payload(value: dict | list | str) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _deserialize_payload(raw: str) -> dict | list | str:
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except Exception:
        return text


def _coerce_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _merge_unique_lists(*values: Any) -> list[str]:
    merged: list[str] = []
    for value in values:
        for item in _coerce_list(value):
            if item not in merged:
                merged.append(item)
    return merged


def _pick_memory_values(memories: list[dict], *, types: set[str] | None = None, key_terms: tuple[str, ...] = (), limit: int = 4) -> list[str]:
    picked: list[str] = []
    for mem in memories:
        if not isinstance(mem, dict):
            continue
        mtype = str(mem.get("type") or "").strip().lower()
        key = str(mem.get("key") or "").strip().lower()
        value = str(mem.get("value") or "").strip()
        if not value:
            continue
        if types and mtype not in types:
            continue
        if key_terms and not any(term in key for term in key_terms):
            continue
        if value not in picked:
            picked.append(value)
        if len(picked) >= limit:
            break
    return picked


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
        data = _deserialize_payload(row["profile_json"])
        if isinstance(data, dict):
            return data
        return {"raw": data}
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
            (user_id, _serialize_payload(profile), _now_ts()),
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
        data = _deserialize_payload(row["state_json"])
        if isinstance(data, dict):
            return data
        return {"raw": data}
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
            (user_id, _serialize_payload(state), _now_ts()),
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
        try:
            data = json.loads(row["model_json"])
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    finally:
        conn.close()


def upsert_personal_model(user_id: str, model: dict | str) -> None:
    conn = _get_conn()
    try:
        if isinstance(model, dict):
            model_json = json.dumps(model, ensure_ascii=False)
        else:
            model_json = str(model)
        conn.execute(
            """
            INSERT INTO personal_model(user_id, model_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              model_json=excluded.model_json,
              updated_at=excluded.updated_at
            """,
            (user_id, model_json, _now_ts()),
        )
        conn.commit()
    finally:
        conn.close()


def update_personal_model_field(user_id: str, field: str, value: Any) -> None:
    """Safe field update for personal model (JSON-backed)."""
    data = get_personal_model(user_id) or {}
    data[str(field)] = value
    upsert_personal_model(user_id, data)


def seed_user_core_profile(user_id: str) -> None:
    """Persist the user's core profile as durable high-priority context."""
    user_id = str(user_id or "").strip()
    if not user_id:
        return

    current_profile = get_profile(user_id) or {}
    merged_profile = dict(current_profile)
    merged_profile.update(CORE_USER_PROFILE)
    upsert_profile(user_id, merged_profile)

    current_model = get_personal_model(user_id) or {}
    merged_model = dict(current_model)
    merged_model.update(CORE_PERSONAL_MODEL)
    for key in {
        "secondary_missions",
        "interests",
        "dislikes",
        "how_to_help",
        "decision_patterns",
        "proactive_focus",
    }:
        merged_model[key] = _merge_unique_lists(CORE_PERSONAL_MODEL.get(key), current_model.get(key))
    upsert_personal_model(user_id, merged_model)

    current_state = get_project_state(user_id) or {}
    merged_state = dict(current_state)
    merged_state.update(CORE_PROJECT_STATE)
    merged_state["active_projects"] = _merge_unique_lists(
        CORE_PROJECT_STATE.get("active_projects"),
        current_state.get("active_projects"),
    )
    merged_state["secondary_missions"] = _merge_unique_lists(
        CORE_PROJECT_STATE.get("secondary_missions"),
        current_state.get("secondary_missions"),
    )
    upsert_project_state(user_id, merged_state)

    for mtype, key, value in CORE_MEMORY_ITEMS:
        upsert_memory(user_id, mtype, key, value)


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


def build_user_brief(
    profile: dict | None,
    personal_model: dict | None,
    recent_memories: list[dict] | None,
    project_state: dict | None,
) -> dict:
    brief: dict = {}
    profile = profile or {}
    personal_model = personal_model or {}
    recent_memories = recent_memories or []
    project_state = project_state or {}

    brief["name"] = profile.get("name") or CORE_USER_PROFILE["name"]
    brief["identity"] = profile.get("identity") or CORE_USER_PROFILE["identity"]
    brief["communication_style"] = (
        personal_model.get("communication_style")
        or personal_model.get("tone")
        or personal_model.get("style")
        or CORE_PERSONAL_MODEL["communication_style"]
    )
    brief["decision_style"] = personal_model.get("decision_style") or CORE_PERSONAL_MODEL["decision_style"]
    brief["current_main_mission"] = (
        personal_model.get("current_main_mission")
        or project_state.get("current_main_mission")
        or CORE_PERSONAL_MODEL["current_main_mission"]
    )

    secondary_missions = _merge_unique_lists(
        CORE_PERSONAL_MODEL.get("secondary_missions"),
        personal_model.get("secondary_missions"),
        project_state.get("secondary_missions"),
    )
    if secondary_missions:
        brief["secondary_missions"] = secondary_missions[:6]

    active_projects = _merge_unique_lists(
        CORE_PROJECT_STATE.get("active_projects"),
        project_state.get("active_projects"),
        _pick_memory_values(recent_memories, types={"project"}, limit=5),
    )
    if active_projects:
        brief["active_projects"] = active_projects[:5]

    interests = _merge_unique_lists(
        CORE_PERSONAL_MODEL.get("interests"),
        personal_model.get("interests"),
    )
    if interests:
        brief["interests"] = interests[:8]

    preferences = _merge_unique_lists(
        ["Sharp direct answers", "No fluff", "Get to the point fast"],
        personal_model.get("preferences"),
        _pick_memory_values(recent_memories, types={"preference"}, limit=5),
    )
    if preferences:
        brief["preferences"] = preferences[:6]

    dislikes = _merge_unique_lists(
        CORE_PERSONAL_MODEL.get("dislikes"),
        personal_model.get("dislikes"),
        _pick_memory_values(recent_memories, types={"dislike"}, key_terms=("dislike", "hate", "avoid"), limit=5),
    )
    if dislikes:
        brief["dislikes"] = dislikes[:6]

    how_to_help = _merge_unique_lists(
        CORE_PERSONAL_MODEL.get("how_to_help"),
        personal_model.get("how_to_help"),
    )
    if how_to_help:
        brief["how_to_help"] = how_to_help[:6]

    decision_patterns = _merge_unique_lists(
        CORE_PERSONAL_MODEL.get("decision_patterns"),
        personal_model.get("decision_patterns"),
    )
    if decision_patterns:
        brief["decision_patterns"] = decision_patterns[:5]

    brief["default_response_mode"] = personal_model.get("default_response_mode") or CORE_PERSONAL_MODEL["default_response_mode"]
    brief["proactive_preference"] = personal_model.get("proactive_preference") or CORE_PERSONAL_MODEL["proactive_preference"]

    proactive_focus = _merge_unique_lists(
        CORE_PERSONAL_MODEL.get("proactive_focus"),
        personal_model.get("proactive_focus"),
    )
    if proactive_focus:
        brief["proactive_focus"] = proactive_focus[:6]

    failure_conditions = _merge_unique_lists(
        CORE_USER_PROFILE.get("failure_conditions"),
        personal_model.get("failure_conditions"),
    )
    if failure_conditions:
        brief["failure_conditions"] = failure_conditions[:5]

    return brief


def load_memory_context_snapshot(
    user_id: str,
    query: str = "",
    *,
    conversation_tail: list[dict] | None = None,
) -> dict:
    seed_user_core_profile(user_id)
    profile = get_profile(user_id)
    personal_model = get_personal_model(user_id) or {}
    recent_memories = list_memories(user_id, limit=12)
    relevant_memories = search_memories(user_id, query, limit=8) if query else recent_memories[:8]
    project_state = get_project_state(user_id)
    user_brief = build_user_brief(profile, personal_model, recent_memories, project_state)
    return {
        "user_profile": profile,
        "user_brief": user_brief,
        "personal_model": personal_model,
        "relevant_memories": relevant_memories,
        "recent_memories": recent_memories,
        "project_state": project_state,
        "conversation_tail": conversation_tail or [],
    }


def format_memory_for_worker(memory_context: dict | None) -> str:
    """
    Keep it short: up to ~12 lines for the worker prompt.
    Expects memory_context with: user_brief, user_profile, relevant_memories, project_state
    """
    if not memory_context:
        return ""

    lines: list[str] = []

    user_brief = memory_context.get("user_brief")
    if user_brief:
        lines.append("USER_BRIEF:")
        lines.append(str(user_brief)[:420])

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
