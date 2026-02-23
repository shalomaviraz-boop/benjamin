# experts/gpt_orchestrator.py
"""
GPT Orchestrator (Brain):
Decides an execution plan + (optional) memory suggestion.
Key rules:
- suggest_memory_write is ONLY a suggestion (never auto-save without explicit "תזכור:")
- memory_to_write must be either a structured object {type,key,value} or null
- key must be <= 40 chars, clean, not a full sentence
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

from openai import AsyncOpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("GPT_ROUTER_MODEL", "gpt-4o-mini")
GOVERNOR_MODEL = os.getenv("GPT_GOVERNOR_MODEL", MODEL)


def _clean_key(raw: str) -> str:
    """Make a short stable key (<=40), no excessive whitespace, no long sentences."""
    if not raw:
        return ""
    k = str(raw).strip()

    # collapse whitespace
    k = re.sub(r"\s+", " ", k)

    # remove surrounding quotes
    k = k.strip('"\'')

    # If it's clearly a sentence (too many words), take first 4-6 words
    words = k.split(" ")
    if len(words) > 6:
        k = " ".join(words[:6])

    # avoid trailing punctuation
    k = k.strip(" .,:;!?-–—")

    # final cap
    if len(k) > 40:
        k = k[:40].rstrip()

    return k


def _validate_memory_obj(mem: Any) -> Optional[dict]:
    """Return sanitized memory object or None."""
    if not isinstance(mem, dict):
        return None

    mtype = str(mem.get("type") or "").strip() or "fact"
    key = _clean_key(mem.get("key") or "")
    value = str(mem.get("value") or "").strip()

    # hard rules
    if not key or not value:
        return None
    if len(key) > 40:
        key = key[:40].rstrip()
    # prevent huge values
    if len(value) > 500:
        value = value[:500].rstrip() + "…"

    return {"type": mtype, "key": key, "value": value}


def _safe_json_loads(s: str) -> dict:
    # Try strict first
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass

    # Fallback: extract first {...} block
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if not m:
        return {}
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _setdefaults(plan: dict) -> dict:
    plan.setdefault("suggested_automation_level", 0)
    plan.setdefault("execution_mode", "direct")  # direct | agent_loop
    plan.setdefault("tools_required", [])
    plan.setdefault("use_web", False)
    plan.setdefault("require_verification", False)
    plan.setdefault("require_code_review", False)
    plan.setdefault("require_task_decomposition", False)
    plan.setdefault("governors", {})
    plan.setdefault("reason", "")
    plan.setdefault("suggest_memory_write", False)
    plan.setdefault("memory_to_write", None)

    # normalize types
    try:
        plan["suggested_automation_level"] = int(plan["suggested_automation_level"])
    except Exception:
        plan["suggested_automation_level"] = 0
    plan["suggested_automation_level"] = max(0, min(5, plan["suggested_automation_level"]))

    if plan["execution_mode"] not in ("direct", "agent_loop"):
        plan["execution_mode"] = "agent_loop" if plan["suggested_automation_level"] >= 3 else "direct"

    if not isinstance(plan["tools_required"], list):
        plan["tools_required"] = []
    plan["tools_required"] = [str(x) for x in plan["tools_required"] if x]

    for b in ("use_web", "require_verification", "require_code_review", "require_task_decomposition", "suggest_memory_write"):
        plan[b] = bool(plan.get(b))

    if not isinstance(plan["governors"], dict):
        plan["governors"] = {}

    if not isinstance(plan["reason"], str):
        plan["reason"] = str(plan["reason"])

    # Governors defaults for higher autonomy (only if user approves later)
    if plan["suggested_automation_level"] >= 4:
        plan["governors"].setdefault("max_execution_time_seconds", 60)
        plan["governors"].setdefault("max_turns", 8)
    elif plan["suggested_automation_level"] == 3:
        plan["governors"].setdefault("max_execution_time_seconds", 45)
        plan["governors"].setdefault("max_turns", 6)

    # Memory: must be structured or null
    mem = _validate_memory_obj(plan.get("memory_to_write"))
    plan["memory_to_write"] = mem
    if not mem:
        plan["suggest_memory_write"] = False

    return plan


SYSTEM_PROMPT = """
אתה ה-LLM Router של "בנימין" (עוזר אישי).
המשימה שלך: להחזיר JSON בלבד (בלי טקסט נוסף) שמחליט איך לבצע את הבקשה.

רמות אוטומציה (0-5):
Level 0 – תשובה בלבד: אין כלים.
Level 1 – כלים לקריאה בלבד: web_search/web_fetch. בלי כתיבה/בלי bash.
Level 2 – איכות + אימות/Code review: שימוש ב-Claude verification / code_review. עדיין בלי bash.
Level 3 – Agent Loop מוגבל: פירוק משימה + צעדים מרובים + refinement. (עדיין bash מוגבל אם קיים במערכת).
Level 4 – חצי אוטונומי: לולאות יותר רחבות + השוואות/אופטימיזציות.
Level 5 – אוטונומי מלא: research עמוק + שיפורים בלי לעצור (אבל תמיד יהיו governors).

כללים:
- ברירת מחדל שמרנית: אם לא צריך כלים/לולאה → Level 0.
- אם צריך מידע עדכני/מזג אוויר/חדשות → use_web=true ולרוב Level 1.
- אם הבקשה היא כתיבת קוד/בדיקת קוד/שיפור קוד → require_code_review=true ולרוב Level 2.
- אם הבקשה מורכבת (ריבוי צעדים/תכנון/מחקר/בניית מערכת) → require_task_decomposition=true ולרוב Level 3+.
- execution_mode:
  - direct ל-Level 0-2
  - agent_loop ל-Level 3-5

Memory (חשוב!):
- אתה רשאי רק "להציע" שמירת זיכרון.
- אם אין משהו איכותי/ברור לשמור → suggest_memory_write=false ו-memory_to_write=null
- אם מציע זיכרון: memory_to_write חייב להיות:
  { "type": "fact"|"preference"|"note"|"project", "key": קצר וברור (<=40 תווים), "value": טקסט קצר }
- אסור לייצר key ארוך/משפט. key חייב להיות "תגית" קצרה.

החזר JSON בלבד בפורמט:
{
  "suggested_automation_level": 0-5,
  "execution_mode": "direct"|"agent_loop",
  "tools_required": [ ... ],
  "use_web": bool,
  "require_verification": bool,
  "require_code_review": bool,
  "require_task_decomposition": bool,
  "governors": { "max_execution_time_seconds"?: int, "max_turns"?: int },
  "reason": "מילה-שתיים למה",
  "suggest_memory_write": bool,
  "memory_to_write": { "type": "...", "key": "...", "value": "..." } | null
}
""".strip()

GOVERNOR_SYSTEM_PROMPT = """
You are Benjamin's internal Governor. Your job is to analyze the user's message against the user's Personal Model and return a SMALL JSON object.
You do NOT answer the user. You only decide how Benjamin should respond.

Return ONLY valid JSON with this schema:
{
  "alignment_score": 0-100,
  "risk_pattern": "overengineering"|"project_switching"|"analysis_paralysis"|"avoidance"|"none",
  "intervention_level": 0|1|2,
  "recommended_action": "answer"|"ask_question"|"reframe"|"push_back",
  "opening_line": "<one short Hebrew line Benjamin should start with if intervention_level>0, otherwise empty>",
  "sharp_question": "<one short Hebrew question to ask before/with the answer if intervention_level>0, otherwise empty>",
  "notes": "<max 120 chars internal note>"
}

Guidelines:
- Be conservative: only intervene when it meaningfully improves focus or prevents distraction.
- Match the user's preference: concise, direct, no long explanations.
- If the user is asking for actionable help that aligns with goals, set intervention_level=0.
- If the user is drifting / starting a new big project / over-architecting, set intervention_level=1 or 2.
""".strip()

PROFILE_EXTRACTOR_SYSTEM_PROMPT = """
You are Benjamin's Profile Extractor.
Your job: detect if the user's message contains durable personal information
that should update the Personal Model.

Return ONLY valid JSON with this schema:
{
  "field": "<string field name or empty>",
  "value": "<string value>",
  "confidence": 0-100,
  "override": true|false
}

Rules:
- Extract ONLY stable traits, goals, preferences, identity facts.
- Ignore temporary states ("אני עייף היום", "בא לי פיצה").
- If nothing durable → return field="" and confidence=0.
- Confidence must reflect how sure you are this is long-term.
- Be conservative.
""".strip()


def _build_user_prompt(message: str, memory_context: Optional[dict]) -> str:
    mc = memory_context or {}
    # keep these short; they are hints, not a full dump
    user_profile = mc.get("user_profile")
    relevant_memories = mc.get("relevant_memories") or []
    project_state = mc.get("project_state")

    def _clip(x: Any, n: int) -> str:
        s = "" if x is None else str(x)
        s = re.sub(r"\s+", " ", s).strip()
        return s[:n]

    lines = []
    if user_profile:
        lines.append("USER_PROFILE: " + _clip(user_profile, 400))
    if relevant_memories:
        lines.append("RELEVANT_MEMORIES:")
        for m in relevant_memories[:8]:
            t = _clip(m.get("type", ""), 30)
            k = _clip(m.get("key", ""), 60)
            v = _clip(m.get("value", ""), 120)
            lines.append(f"- ({t}) {k}: {v}")
    if project_state:
        lines.append("PROJECT_STATE: " + _clip(project_state, 400))

    lines.append("USER_MESSAGE: " + message)
    return "\n".join(lines)


class GPTOrchestrator:
    def __init__(self) -> None:
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not set in .env (required for GPT orchestrator)")
        self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    async def decide(self, message: str, memory_context: Optional[dict] = None) -> dict:
        user_prompt = _build_user_prompt(message, memory_context)

        resp = await self.client.chat.completions.create(
            model=MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

        text = (resp.choices[0].message.content or "").strip()
        plan = _safe_json_loads(text)
        return _setdefaults(plan)

    async def analyze_governor(self, message: str, personal_model: Optional[dict] = None) -> dict:
        """Return governor guidance JSON (internal)."""
        user_prompt = json.dumps(
            {
                "message": message,
                "personal_model": personal_model or {},
            },
            ensure_ascii=False,
        )

        resp = await self.client.chat.completions.create(
            model=GOVERNOR_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": GOVERNOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

        text = (resp.choices[0].message.content or "").strip()
        out = _safe_json_loads(text) or {}

        # Minimal defaults / type safety
        try:
            out["alignment_score"] = int(out.get("alignment_score", 50))
        except Exception:
            out["alignment_score"] = 50

        if out.get("risk_pattern") not in {
            "overengineering",
            "project_switching",
            "analysis_paralysis",
            "avoidance",
            "none",
        }:
            out["risk_pattern"] = "none"

        if out.get("recommended_action") not in {"answer", "ask_question", "reframe", "push_back"}:
            out["recommended_action"] = "answer"

        try:
            out["intervention_level"] = int(out.get("intervention_level", 0))
        except Exception:
            out["intervention_level"] = 0
        out["intervention_level"] = max(0, min(2, out["intervention_level"]))

        out["opening_line"] = (out.get("opening_line") or "").strip()[:140]
        out["sharp_question"] = (out.get("sharp_question") or "").strip()[:200]
        out["notes"] = (out.get("notes") or "").strip()[:120]

        return out

    async def extract_profile_update(self, message: str) -> dict:
        """Detect durable profile updates from user message."""
        resp = await self.client.chat.completions.create(
            model=MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": PROFILE_EXTRACTOR_SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
        )

        text = (resp.choices[0].message.content or "").strip()
        out = _safe_json_loads(text) or {}

        field = str(out.get("field") or "").strip()
        value = str(out.get("value") or "").strip()
        try:
            confidence = int(out.get("confidence", 0))
        except Exception:
            confidence = 0
        override = bool(out.get("override", False))

        if confidence < 75 or not field or not value:
            return {"should_update": False}

        # basic limits
        field = field[:40]
        value = value[:300]

        return {
            "should_update": True,
            "field": field,
            "value": value,
            "override": override,
            "confidence": confidence,
        }