"""Global breaking alerts with verification, dedupe, and cluster cooldown."""

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram.ext import ContextTypes

from experts.gemini_client import generate_web

from agents.memory_agent import MemoryAgent
from agents.priority_agent import PriorityAgent
from agents.quality_agent import QualityAgent

_STATE_DB_PATH = Path(__file__).resolve().parent.parent / "proactive_state.db"
ALERT_CLUSTER_COOLDOWN_HOURS = 12
MAX_CONTRADICTION_RISK = 35
SUPPORTED_CATEGORIES = {
    "global",
    "israel",
    "markets",
    "ai",
    "geopolitics",
    "regulation",
    "tech",
    "security",
    "energy",
}
CATEGORY_PREFIX = {
    "global": "גלובלי",
    "israel": "ישראל",
    "markets": "שוק",
    "ai": "AI",
    "geopolitics": "גיאופוליטי",
    "regulation": "רגולציה",
    "tech": "טכנולוגיה",
    "security": "ביטחוני",
    "energy": "אנרגיה",
}


def _state_conn():
    conn = sqlite3.connect(_STATE_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sent_alerts (
            dedupe_key TEXT PRIMARY KEY,
            category TEXT,
            sent_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return conn


def _clusters_conn():
    conn = sqlite3.connect(_STATE_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_clusters (
            cluster_key TEXT PRIMARY KEY,
            category TEXT,
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return conn


def _cluster_seen(cluster_key: str, cooldown_hours: int = ALERT_CLUSTER_COOLDOWN_HOURS) -> bool:
    if not cluster_key:
        return False
    conn = _clusters_conn()
    try:
        row = conn.execute(
            "SELECT last_seen FROM event_clusters WHERE cluster_key = ?",
            (cluster_key,),
        ).fetchone()
        if row is None or not row[0]:
            return False
        try:
            last_seen = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
        except Exception:
            return True
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=cooldown_hours)
        return last_seen >= cutoff
    finally:
        conn.close()


def _mark_cluster(cluster_key: str, category: str) -> None:
    if not cluster_key:
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = _clusters_conn()
    try:
        conn.execute(
            """
            INSERT INTO event_clusters (cluster_key, category, first_seen, last_seen)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cluster_key) DO UPDATE SET
                category=excluded.category,
                last_seen=excluded.last_seen
            """,
            (cluster_key, category, now_iso, now_iso),
        )
        conn.commit()
    finally:
        conn.close()


def _normalize_dedupe_key(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _alert_already_sent(dedupe_key: str) -> bool:
    key = _normalize_dedupe_key(dedupe_key)
    if not key:
        return False
    conn = _state_conn()
    try:
        row = conn.execute(
            "SELECT dedupe_key FROM sent_alerts WHERE dedupe_key = ?",
            (key,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _mark_alert_sent(dedupe_key: str, category: str) -> None:
    key = _normalize_dedupe_key(dedupe_key)
    if not key:
        return
    conn = _state_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO sent_alerts (dedupe_key, category) VALUES (?, ?)",
            (key, category),
        )
        conn.commit()
    finally:
        conn.close()


def _extract_json_object(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        data = json.loads(raw[start : end + 1])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normalize_cluster_key(category: str, cluster: str, headline: str) -> str:
    cat = (category or "").strip().lower()
    cl = re.sub(r"\s+", "", (cluster or "").strip().lower())[:80]
    hl = re.sub(r"\s+", "", (headline or "").strip().lower())[:80]
    return f"{cat}:{cl or hl}"


def _normalize_category(category: str) -> str:
    cat = (category or "").strip().lower()
    return cat if cat in SUPPORTED_CATEGORIES else ""


async def _verify_breaking_candidate(raw_candidate: str) -> dict:
    """Second-pass verification gate for breaking alerts."""
    prompt = (
        "אתה שכבת אימות להתראות חדשות. קיבלת טיוטת JSON של אירוע אפשרי.\n"
        "המטרה שלך: להחזיר JSON מאומת בלבד, ולפסול כל דבר לא ודאי, כפול או ספקולטיבי.\n"
        "\n"
        "האירוע לבדיקה:\n"
        f"{raw_candidate}\n"
        "\n"
        "החזר JSON בלבד בפורמט הזה:\n"
        "{\n"
        '  "should_send": true/false,\n'
        '  "category": "global" | "israel" | "markets" | "ai" | "security" | "geopolitics" | "regulation" | "tech" | "energy" | "",\n'
        '  "headline": "כותרת קצרה בעברית",\n'
        '  "summary": "2-3 שורות בעברית, חד וברור",\n'
        '  "why_it_matters": "שורה אחת בעברית",\n'
        '  "severity": "high" | "critical" | "",\n'
        '  "confidence": 0-100,\n'
        '  "source_count": 0-10,\n'
        '  "contradiction_risk": 0-100,\n'
        '  "event_cluster": "תגית קצרה ויציבה לאירוע",\n'
        '  "dedupe_key": "מזהה קצר ויציב לאירוע"\n'
        "}\n"
        "\n"
        "כללים קשיחים:\n"
        "- אל תמציא עובדות או חברות או מספרים.\n"
        "- אם אין ודאות גבוהה: should_send=false.\n"
        "- אם category לא מתוך הרשימה המותרת: category=\"\" ו-should_send=false.\n"
        "- אם נראה שזה אותו אירוע שכבר יכול להישלח שוב בניסוח אחר, החזר event_cluster יציב.\n"
        "- שלח התראה רק אם confidence>=85 וגם source_count>=2 וגם contradiction_risk<=35.\n"
        "- בלי טקסט מחוץ ל-JSON.\n"
    )
    raw = await generate_web(prompt)
    return _extract_json_object(raw)


class BreakingAgent:
    async def _detect_breaking_candidate_raw(self) -> str:
        prompt = (
            "אתר אם קרה ממש עכשיו אירוע חריג ומשמעותי באמת שמצדיק התראה מיידית.\n"
            "התמקד באירועים מהותיים בעולם בלבד, בקטגוריות הבאות:\n"
            "1. global - אירוע גלובלי רחב עם השפעה מהותית\n"
            "2. israel - אירוע ישראלי חשוב עם השפעה מהותית\n"
            "3. markets - שוקי הון, מדדים, תשואות, נפט, תנועות שוק חריגות\n"
            "4. ai - הכרזות/השקות/מימון/רגולציה/מהלכים מהותיים של שחקני AI\n"
            "5. security - אירועי סייבר/ביטחון בעלי השפעה מהותית\n"
            "6. geopolitics - אירועים מדינתיים/בינלאומיים עם השפעה גלובלית\n"
            "7. regulation - צעדי רגולציה משמעותיים המשפיעים על שווקים/טכנולוגיה\n"
            "8. tech - אירועי טכנולוגיה גדולים עם השפעה עסקית רחבה\n"
            "9. energy - אירועי אנרגיה משמעותיים (נפט/גז/חשמל/אספקה)\n"
            "\n"
            "החזר JSON בלבד בפורמט הזה:\n"
            "{\n"
            '  "should_send": true/false,\n'
            '  "category": "global" | "israel" | "markets" | "ai" | "security" | "geopolitics" | "regulation" | "tech" | "energy" | "",\n'
            '  "headline": "כותרת קצרה בעברית",\n'
            '  "summary": "2-3 שורות בעברית, חד וברור",\n'
            '  "why_it_matters": "שורה אחת בעברית",\n'
            '  "severity": "high" | "critical" | "",\n'
            '  "event_cluster": "תגית קצרה ויציבה לאירוע",\n'
            '  "dedupe_key": "מזהה קצר ויציב לאירוע"\n'
            "}\n"
            "\n"
            "כללים:\n"
            "- בלי שאלות.\n"
            "- בלי טקסט מחוץ ל-JSON.\n"
            "- אם אין אירוע חשוב באמת: should_send=false.\n"
            "- אם category לא מתוך הרשימה, החזר category=\"\" וגם should_send=false.\n"
            "- אל תמציא אירועים. אם לא בטוח: should_send=false.\n"
            "- החזר רק אירוע אחד לכל ריצה: החשוב ביותר כרגע.\n"
        )
        return await generate_web(prompt)

    async def detect(self) -> str:
        return await self._detect_breaking_candidate_raw()

    async def verify(self, raw_candidate: str) -> dict:
        return await _verify_breaking_candidate(raw_candidate)

    def should_send(self, verified: dict) -> bool:
        if not verified or not bool(verified.get("should_send")):
            return False
        confidence = int(verified.get("confidence") or 0)
        source_count = int(verified.get("source_count") or 0)
        severity = (verified.get("severity") or "").strip().lower()
        category = _normalize_category(verified.get("category"))
        contradiction_risk = float(verified.get("contradiction_risk") or 100)
        if not category:
            return False
        verified["category"] = category
        if confidence < 85 or source_count < 2:
            return False
        if contradiction_risk > MAX_CONTRADICTION_RISK:
            return False
        if severity not in {"high", "critical"}:
            return False
        return True

    def build_keys(self, verified: dict) -> tuple[str, str, str]:
        category = _normalize_category(verified.get("category"))
        headline = (verified.get("headline") or "").strip()
        event_cluster = (verified.get("event_cluster") or "").strip()
        dedupe_key = (verified.get("dedupe_key") or "").strip()
        cluster_key = _normalize_cluster_key(category, event_cluster, headline)
        return category, cluster_key, (dedupe_key or cluster_key)

    def format_text(self, verified: dict) -> str:
        category = _normalize_category(verified.get("category"))
        headline = (verified.get("headline") or "").strip()
        summary = (verified.get("summary") or "").strip()
        why_it_matters = (verified.get("why_it_matters") or "").strip()
        severity = (verified.get("severity") or "").strip().lower()
        label = CATEGORY_PREFIX.get(category, "עדכון")

        if severity == "critical":
            prefix = f"🚨🚨 {label}"
        else:
            prefix = f"🚨 {label}"

        text = f"{prefix} | {headline}\n\n{summary}"
        if why_it_matters:
            text += f"\n\n🎯 למה זה חשוב:\n{why_it_matters}"
        return text

    async def run_check(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        quality: QualityAgent,
        priority: PriorityAgent,
        memory: MemoryAgent,
    ) -> None:
        """Checks for important global breaking events and pushes immediately."""
        try:
            chat_id = context.job.data.get("chat_id")
            if not chat_id:
                return

            raw_candidate = await self.detect()
            candidate = _extract_json_object(raw_candidate)
            if not candidate or not bool(candidate.get("should_send")):
                return

            verified = await self.verify(raw_candidate)
            verified["category"] = _normalize_category(verified.get("category"))
            if not verified.get("category"):
                return
            if not self.should_send(verified):
                return

            scored = await priority.score_event(verified)
            print(f"Priority score: {scored.get('priority_score')}")
            if not scored.get("should_send"):
                return

            category = (verified.get("category") or "").strip()
            topic_key = memory.get_topic_key(verified)
            if not memory.should_allow_event(topic_key):
                if not memory.is_major_change(topic_key, verified):
                    memory.update_event(topic_key, category, sent=False, verified=verified)
                    return

            category, cluster_key, dedupe_key = self.build_keys(verified)

            if _cluster_seen(cluster_key, cooldown_hours=ALERT_CLUSTER_COOLDOWN_HOURS) or _alert_already_sent(
                dedupe_key
            ):
                return

            text = self.format_text(verified)
            text = await quality.polish(text)

            await context.bot.send_message(chat_id=chat_id, text=text)
            _mark_cluster(cluster_key, category)
            _mark_alert_sent(dedupe_key, category)
            memory.update_event(topic_key, category, sent=True, verified=verified)
            print(
                f"Breaking alert sent: {category} | {verified.get('headline')} | cluster={cluster_key}"
            )

        except Exception as e:
            print(f"Breaking events job error: {e}")
