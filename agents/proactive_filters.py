"""Shared dedup, cooldown, and relevance filters for proactive pipelines.

All proactive paths (breaking alerts, scheduled reports) must pass through
these gates so we never spam Matan with near-duplicates of the same theme.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

_STATE_DB_PATH = Path(__file__).resolve().parent.parent / "proactive_state.db"

DEFAULT_COOLDOWN_HOURS = 24
CRITICAL_COOLDOWN_HOURS = 6
SIMILARITY_LOOKBACK_HOURS = 48
SIMILARITY_THRESHOLD = 0.30
HEADLINE_SIMILARITY_THRESHOLD = 0.35
MAX_PROACTIVE_PER_DAY = 4

# News verbs/glue that should not contribute to dedup signal
_DEDUP_GLUE = {
    "launches", "launched", "launch", "release", "released", "releases", "announces",
    "announced", "announcement", "today", "yesterday", "now", "with", "via", "from",
    "after", "ahead", "of", "the", "a", "an", "and", "or", "to", "for", "into",
    "on", "in", "at", "by", "is", "are", "was", "were",
    "מכריזה", "השיקה", "משיקה", "השיק", "הכריזה", "הכריז", "פרסם", "פרסמה",
    "היום", "עכשיו", "אחרי", "לפני",
}

ALLOWED_BROADCAST_CATEGORIES = {
    "ai",
    "business",
    "project",
    "markets",
    "personal",
    "ai_release",
    "ai_news",
    "macro",
    "geopolitics",
    "regulation",
    "tech",
    "energy",
    "global",
    "israel",
    "security",
}

# Categories where we accept higher-frequency alerts only if marked critical.
CRITICAL_ONLY_CATEGORIES = {"geopolitics", "global", "israel", "security"}

USER_GOAL_KEYWORDS = (
    "super agent", "סופר אייג'נט", "benjamin", "בנימין",
    "ai", "openai", "anthropic", "google", "gemini", "claude", "gpt", "llm",
    "agent", "אייג'נט", "automation", "workflow", "saas", "startup", "סטארטאפ",
    "leverage", "מינוף", "growth", "monetization", "מוניטיזציה",
    "business", "עסק", "income", "revenue", "השקעה", "investment",
    "macro", "מאקרו", "stocks", "מניות", "market", "שוק",
    "fitness_goal", "career_target_role", "finance_savings_goal",
    "finance_income_goal", "finance_investment_goal",
)

_TOKEN_RE = re.compile(r"[\w\u0590-\u05FF]{3,}", re.UNICODE)
_HE_STOPWORDS = {
    "אבל", "וגם", "וכן", "וזה", "אתה", "הוא", "היא", "כמו", "מאוד", "רק", "כדי", "האם",
    "פה", "שם", "כל", "אחת", "אחד", "להיות", "יותר", "פחות",
    "with", "this", "that", "from", "have", "will", "what", "your", "just", "into",
    "after", "very", "more", "less", "than", "they", "them", "their",
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_STATE_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS proactive_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            category TEXT,
            theme_key TEXT,
            fingerprint TEXT,
            headline TEXT,
            summary TEXT,
            severity TEXT,
            relevance_score INTEGER,
            sent_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_proactive_log_user_time ON proactive_log(user_id, sent_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_proactive_log_theme ON proactive_log(theme_key, sent_at DESC)"
    )
    conn.commit()
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _tokens(text: str) -> set[str]:
    if not text:
        return set()
    return {tok.lower() for tok in _TOKEN_RE.findall(text) if tok.lower() not in _HE_STOPWORDS}


def _content_tokens(text: str) -> set[str]:
    """Tokens with news-verb glue removed and short variants normalized."""
    if not text:
        return set()
    out: set[str] = set()
    for tok in _TOKEN_RE.findall(text):
        low = tok.lower()
        if low in _HE_STOPWORDS or low in _DEDUP_GLUE:
            continue
        # crude singularization of common english plural endings
        if len(low) > 5 and low.endswith("es"):
            low = low[:-2]
        elif len(low) > 4 and low.endswith("s"):
            low = low[:-1]
        out.add(low)
    return out


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    return inter / union


def normalize_theme_key(category: str, headline: str, cluster: str = "") -> str:
    cat = (category or "general").strip().lower()
    base = (cluster or headline or "").strip().lower()
    base = re.sub(r"[^\w\u0590-\u05FF\s]", "", base)
    base = re.sub(r"\s+", "_", base)[:60]
    return f"{cat}:{base}" if base else cat


def fingerprint_text(*chunks: str) -> str:
    joined = " ".join(c for c in chunks if c)
    tokens = sorted(_tokens(joined))[:24]
    return ":".join(tokens)


def category_allowed(category: str) -> bool:
    return (category or "").strip().lower() in ALLOWED_BROADCAST_CATEGORIES


def relevance_score(candidate: dict, memory_context: dict | None) -> int:
    """0-100 score: how relevant this proactive candidate is to the user's stated goals."""
    if not candidate:
        return 0
    text_parts = [
        str(candidate.get("headline") or ""),
        str(candidate.get("summary") or ""),
        str(candidate.get("why_relevant") or candidate.get("why_it_matters") or ""),
        str(candidate.get("opportunity") or ""),
        str(candidate.get("category") or ""),
    ]
    text = " ".join(text_parts).lower()
    if not text.strip():
        return 0

    score = 0
    for kw in USER_GOAL_KEYWORDS:
        if kw.lower() in text:
            score += 6

    severity = (candidate.get("severity") or "").lower()
    if severity == "critical":
        score += 25
    elif severity == "high":
        score += 12

    confidence = int(candidate.get("confidence") or 0)
    score += min(confidence // 4, 25)

    if memory_context and isinstance(memory_context, dict):
        ret = memory_context.get("retrieval_summary") or {}
        anchor_terms: list[str] = []
        for key in ("identity", "projects", "strategic", "tone"):
            anchor_terms.extend([str(v) for v in (ret.get(key) or []) if v])
        anchor_text = " ".join(anchor_terms).lower()
        if anchor_text:
            shared = len(_tokens(text) & _tokens(anchor_text))
            score += min(shared * 3, 25)

    return min(score, 100)


def is_duplicate_or_cooling_down(
    user_id: str,
    *,
    candidate: dict,
    theme_key: str,
    fingerprint: str,
) -> tuple[bool, str]:
    """Returns (blocked, reason). Blocks if same theme within cooldown, or fingerprint similar within window."""
    severity = (candidate.get("severity") or "").lower()
    cooldown_hours = CRITICAL_COOLDOWN_HOURS if severity == "critical" else DEFAULT_COOLDOWN_HOURS
    cutoff_cooldown = datetime.now(timezone.utc) - timedelta(hours=cooldown_hours)
    cutoff_similarity = datetime.now(timezone.utc) - timedelta(hours=SIMILARITY_LOOKBACK_HOURS)
    cutoff_daily = datetime.now(timezone.utc) - timedelta(hours=24)

    conn = _conn()
    try:
        rows = conn.execute(
            """
            SELECT theme_key, fingerprint, headline, summary, sent_at
            FROM proactive_log
            WHERE user_id = ? AND sent_at >= ?
            ORDER BY sent_at DESC
            LIMIT 80
            """,
            (str(user_id or "default"), cutoff_similarity.isoformat()),
        ).fetchall()
    finally:
        conn.close()

    sent_today = 0
    candidate_headline = str(candidate.get("headline") or "")
    candidate_full = f"{candidate_headline} {str(candidate.get('summary') or '')}"
    candidate_headline_tokens = _content_tokens(candidate_headline)
    candidate_full_tokens = _content_tokens(candidate_full)
    candidate_fp_tokens = set(fingerprint.split(":")) if fingerprint else set()

    for theme_prev, fp_prev, headline_prev, summary_prev, sent_at in rows:
        sent_dt = _parse_iso(sent_at)
        if sent_dt is None:
            continue
        if sent_dt >= cutoff_daily:
            sent_today += 1
        if theme_prev == theme_key and sent_dt >= cutoff_cooldown:
            if severity == "critical":
                continue
            return True, f"theme cooldown: {theme_key} sent at {sent_at}"
        prev_full_tokens = _content_tokens(f"{headline_prev or ''} {summary_prev or ''}")
        prev_headline_tokens = _content_tokens(headline_prev or "")
        full_sim = _jaccard(candidate_full_tokens, prev_full_tokens)
        head_sim = _jaccard(candidate_headline_tokens, prev_headline_tokens)
        fp_sim = _jaccard(candidate_fp_tokens, set((fp_prev or "").split(":")))
        if sent_dt >= cutoff_cooldown and (
            full_sim >= SIMILARITY_THRESHOLD
            or head_sim >= HEADLINE_SIMILARITY_THRESHOLD
            or fp_sim >= SIMILARITY_THRESHOLD
        ):
            return True, (
                f"semantic dup: full={full_sim:.2f} head={head_sim:.2f} fp={fp_sim:.2f} "
                f"vs '{(headline_prev or '')[:40]}'"
            )

    if sent_today >= MAX_PROACTIVE_PER_DAY and severity != "critical":
        return True, f"daily cap reached: {sent_today}/{MAX_PROACTIVE_PER_DAY}"

    return False, ""


def record_send(
    user_id: str,
    *,
    category: str,
    theme_key: str,
    fingerprint: str,
    headline: str,
    summary: str,
    severity: str,
    relevance: int,
) -> None:
    conn = _conn()
    try:
        conn.execute(
            """
            INSERT INTO proactive_log
                (user_id, category, theme_key, fingerprint, headline, summary, severity, relevance_score, sent_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(user_id or "default"),
                (category or "").strip().lower(),
                theme_key,
                fingerprint,
                (headline or "")[:240],
                (summary or "")[:480],
                (severity or "").strip().lower(),
                int(relevance or 0),
                _now_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def gate_proactive_candidate(
    *,
    user_id: str,
    candidate: dict,
    memory_context: dict | None = None,
    min_relevance: int = 45,
) -> dict:
    """Single entry point. Returns {allowed, reason, theme_key, fingerprint, relevance}."""
    if not candidate or not bool(candidate.get("should_send")):
        return {"allowed": False, "reason": "candidate.should_send=False"}

    category = (candidate.get("category") or "").strip().lower()
    if not category_allowed(category):
        return {"allowed": False, "reason": f"category not allowed: {category!r}"}

    severity = (candidate.get("severity") or "").lower()
    if category in CRITICAL_ONLY_CATEGORIES and severity not in {"high", "critical"}:
        return {"allowed": False, "reason": f"category {category} requires high/critical severity"}

    relevance = relevance_score(candidate, memory_context)
    if relevance < min_relevance and severity != "critical":
        return {"allowed": False, "reason": f"relevance {relevance} < {min_relevance}"}

    headline = str(candidate.get("headline") or "").strip()
    summary = str(candidate.get("summary") or "").strip()
    cluster = str(candidate.get("event_cluster") or "").strip()
    theme_key = normalize_theme_key(category, headline, cluster)
    fingerprint = fingerprint_text(headline, summary, str(candidate.get("why_relevant") or ""))

    blocked, reason = is_duplicate_or_cooling_down(
        user_id,
        candidate=candidate,
        theme_key=theme_key,
        fingerprint=fingerprint,
    )
    if blocked:
        return {"allowed": False, "reason": reason, "theme_key": theme_key, "fingerprint": fingerprint, "relevance": relevance}

    return {
        "allowed": True,
        "reason": "ok",
        "theme_key": theme_key,
        "fingerprint": fingerprint,
        "relevance": relevance,
    }


def commit_send(
    user_id: str,
    *,
    candidate: dict,
    gate_result: dict,
) -> None:
    if not gate_result.get("allowed"):
        return
    record_send(
        user_id,
        category=str(candidate.get("category") or "").strip().lower(),
        theme_key=gate_result.get("theme_key") or "",
        fingerprint=gate_result.get("fingerprint") or "",
        headline=str(candidate.get("headline") or "").strip(),
        summary=str(candidate.get("summary") or "").strip(),
        severity=str(candidate.get("severity") or "").strip().lower(),
        relevance=int(gate_result.get("relevance") or 0),
    )


def recent_sent_summary(user_id: str, hours: int = 24) -> list[dict]:
    """For debugging / introspection."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn = _conn()
    try:
        rows = conn.execute(
            """
            SELECT category, theme_key, headline, severity, relevance_score, sent_at
            FROM proactive_log
            WHERE user_id = ? AND sent_at >= ?
            ORDER BY sent_at DESC
            """,
            (str(user_id or "default"), cutoff),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "category": r[0],
            "theme_key": r[1],
            "headline": r[2],
            "severity": r[3],
            "relevance": r[4],
            "sent_at": r[5],
        }
        for r in rows
    ]
