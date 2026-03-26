"""Event memory for suppressing repeated narrative noise."""

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

_STATE_DB_PATH = Path(__file__).resolve().parent.parent / "proactive_state.db"


class MemoryAgent:
    def __init__(self):
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
            # Backward-compatible migration for existing DBs.
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
            # Major-change override can be added later.
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

    def _severity_rank(self, severity: str) -> int:
        sev = (severity or "").strip().lower()
        if sev == "critical":
            return 2
        if sev == "high":
            return 1
        return 0

    def _normalize_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", (value or "").strip().lower())

    def _text_is_materially_new(self, previous: str, current: str) -> bool:
        prev = self._normalize_text(previous)
        curr = self._normalize_text(current)
        if not curr:
            return False
        if not prev:
            return True
        if prev == curr:
            return False
        prev_tokens = set(prev.split())
        curr_tokens = set(curr.split())
        union = prev_tokens | curr_tokens
        overlap = len(prev_tokens & curr_tokens) / len(union) if union else 1.0
        return overlap < 0.6

    def is_major_change(self, topic_key: str, verified: dict) -> bool:
        if not topic_key:
            return False
        conn = self._conn()
        try:
            row = conn.execute(
                """
                SELECT last_sent, last_headline, last_summary, last_severity
                FROM event_memory
                WHERE topic_key = ?
                """,
                (topic_key,),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return True

        last_sent_raw, prev_headline, prev_summary, prev_severity = row
        curr_headline = (verified.get("headline") or "").strip()
        curr_summary = (verified.get("summary") or "").strip()
        curr_severity = (verified.get("severity") or "").strip()

        if self._severity_rank(curr_severity) > self._severity_rank(prev_severity or ""):
            return True

        prev_risk = float(verified.get("previous_contradiction_risk") or 0)
        curr_risk = float(verified.get("contradiction_risk") or 0)
        if prev_risk > 0 and (prev_risk - curr_risk) >= 20:
            return True

        if self._text_is_materially_new(prev_headline or "", curr_headline):
            return True
        if self._text_is_materially_new(prev_summary or "", curr_summary):
            return True

        confidence = int(verified.get("confidence") or 0)
        if last_sent_raw and confidence >= 95:
            try:
                last_sent = datetime.fromisoformat(str(last_sent_raw).replace("Z", "+00:00"))
                if last_sent.tzinfo is None:
                    last_sent = last_sent.replace(tzinfo=timezone.utc)
                if last_sent <= datetime.now(timezone.utc) - timedelta(hours=6):
                    return True
            except Exception:
                return False

        return False

    def update_event(self, topic_key: str, category: str, sent: bool, verified: dict):
        if not topic_key:
            return
        now_iso = datetime.now(timezone.utc).isoformat()
        last_sent = now_iso if sent else None
        headline = (verified.get("headline") or "").strip()
        summary = (verified.get("summary") or "").strip()
        severity = (verified.get("severity") or "").strip().lower()
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO event_memory (
                    topic_key,
                    category,
                    first_seen,
                    last_seen,
                    mention_count,
                    last_sent,
                    last_headline,
                    last_summary,
                    last_severity
                )
                VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                ON CONFLICT(topic_key) DO UPDATE SET
                    category=excluded.category,
                    last_seen=excluded.last_seen,
                    mention_count=event_memory.mention_count + 1,
                    last_sent=CASE
                        WHEN excluded.last_sent IS NOT NULL THEN excluded.last_sent
                        ELSE event_memory.last_sent
                    END,
                    last_headline=excluded.last_headline,
                    last_summary=excluded.last_summary,
                    last_severity=excluded.last_severity
                """,
                (topic_key, category, now_iso, now_iso, last_sent, headline, summary, severity),
            )
            conn.commit()
        finally:
            conn.close()
