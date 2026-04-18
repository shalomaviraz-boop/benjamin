"""Event memory for suppressing repeated narrative noise."""

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agents.agent_context import read_shared_context
from agents.agent_contract import build_agent_result
from agents.base_agent import BaseAgent
from memory.memory_store import delete_memories_by_key, search_memories, upsert_memory

_STATE_DB_PATH = Path(__file__).resolve().parent.parent / "proactive_state.db"


class MemoryAgent(BaseAgent):
    def __init__(self):
        super().__init__("memory", "Reads and writes Benjamin memory.")
        self._ensure_table()

    def _conn(self):
        return sqlite3.connect(_STATE_DB_PATH)

    def _ensure_table(self) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS event_memory (
                    topic_key TEXT PRIMARY KEY,
                    category TEXT,
                    first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                    mention_count INTEGER DEFAULT 0,
                    last_sent DATETIME,
                    last_headline TEXT,
                    last_summary TEXT,
                    last_severity TEXT
                )
                """
            )
            for column_sql in (
                "ALTER TABLE event_memory ADD COLUMN last_headline TEXT",
                "ALTER TABLE event_memory ADD COLUMN last_summary TEXT",
                "ALTER TABLE event_memory ADD COLUMN last_severity TEXT",
            ):
                try:
                    conn.execute(column_sql)
                except sqlite3.OperationalError:
                    pass
            conn.commit()
        finally:
            conn.close()

    async def run(self, task: dict, context: dict) -> dict:
        shared = read_shared_context(task, context)
        message = (shared.user_message or task.get("message") or "").strip()
        plan = shared.task or task.get("plan") or {}
        user_id = str(((context or {}).get("orchestrator_context") or {}).get("user_id") or (context or {}).get("user_id") or "default")

        memory_to_write = plan.get("memory_to_write") if isinstance(plan.get("memory_to_write"), dict) else None
        if plan.get("suggest_memory_write") and memory_to_write:
            key = str(memory_to_write.get("key") or "general").strip() or "general"
            value = str(memory_to_write.get("value") or "").strip()
            mtype = str(memory_to_write.get("type") or "fact").strip() or "fact"
            if value:
                upsert_memory(user_id, key, value, mtype)
                result = build_agent_result(
                    agent=self.name,
                    output=value,
                    notes=f"memory saved: {key}",
                    data={"action": "write", "key": key, "type": mtype},
                    agent_context=shared.to_dict(),
                )
                shared.add_log(self.name, f"memory write: {key}")
                result["agent_context"] = shared.to_dict()
                return result

        lowered = message.lower()
        if lowered.startswith("שכח") or lowered.startswith("forget"):
            key = message.split(":", 1)[-1].strip() if ":" in message else message.split(" ", 1)[-1].strip()
            if key:
                deleted = delete_memories_by_key(user_id, key)
                result = build_agent_result(
                    agent=self.name,
                    output=f"deleted {deleted}",
                    notes=f"memory deleted: {key}",
                    data={"action": "delete", "key": key, "deleted": deleted},
                    agent_context=shared.to_dict(),
                )
                shared.add_log(self.name, f"memory delete: {key}")
                result["agent_context"] = shared.to_dict()
                return result

        query = message.split(":", 1)[-1].strip() if ":" in message else message
        results = search_memories(user_id, query, limit=5)
        output = "\n".join(f"- {item.get('key')}: {item.get('value')}" for item in results if item.get("value"))
        result = build_agent_result(
            agent=self.name,
            output=output,
            notes="memory lookup completed" if output else "no memory match",
            data={"action": "read", "count": len(results)},
            agent_context=shared.to_dict(),
        )
        shared.add_log(self.name, f"memory read: {len(results)} matches")
        result["agent_context"] = shared.to_dict()
        return result

    def get_topic_key(self, verified: dict) -> str:
        category = (verified.get("category") or "").strip().lower()
        cluster = (verified.get("event_cluster") or "").strip().lower()
        headline = (verified.get("headline") or "").strip().lower()
        topic = cluster or headline
        topic = re.sub(r"\s+", "", topic)[:100]
        return f"{category}:{topic}"

    def should_allow_event(self, topic_key: str) -> bool:
        if not topic_key:
            return True
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT mention_count, last_sent FROM event_memory WHERE topic_key = ?",
                (topic_key,),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return True

        mention_count = int(row[0] or 0)
        last_sent_raw = row[1]

        if mention_count > 5:
            return False

        if mention_count > 3 and last_sent_raw:
            try:
                last_sent = datetime.fromisoformat(str(last_sent_raw).replace("Z", "+00:00"))
                if last_sent.tzinfo is None:
                    last_sent = last_sent.replace(tzinfo=timezone.utc)
                if last_sent >= datetime.now(timezone.utc) - timedelta(hours=3):
                    return False
            except Exception:
                return False
        return True

    def mark_event(self, topic_key: str, category: str, headline: str, summary: str, severity: str, *, sent: bool) -> None:
        if not topic_key:
            return
        conn = self._conn()
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO event_memory (topic_key, category, first_seen, last_seen, mention_count, last_sent, last_headline, last_summary, last_severity)
                VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                ON CONFLICT(topic_key) DO UPDATE SET
                    category=excluded.category,
                    last_seen=excluded.last_seen,
                    mention_count=event_memory.mention_count + 1,
                    last_sent=CASE WHEN excluded.last_sent IS NOT NULL THEN excluded.last_sent ELSE event_memory.last_sent END,
                    last_headline=excluded.last_headline,
                    last_summary=excluded.last_summary,
                    last_severity=excluded.last_severity
                """,
                (
                    topic_key,
                    category,
                    now_iso,
                    now_iso,
                    now_iso if sent else None,
                    headline,
                    summary,
                    severity,
                ),
            )
            conn.commit()
        finally:
            conn.close()
