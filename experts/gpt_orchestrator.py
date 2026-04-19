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


VALID_MEMORY_TYPES = {
    "identity",
    "preference",
    "project",
    "behavioral",
    "relational",
    "temporal",
    "strategic",
    "fact",
    "profile",
    "goal",
    "note",
    "dislike",
}


def _normalize_memory_type(raw: Any) -> str:
    value = str(raw or "").strip().lower() or "identity"
    aliases = {
        "fact": "identity",
        "profile": "identity",
        "goal": "strategic",
        "note": "temporal",
        "dislike": "preference",
    }
    return aliases.get(value, value if value in VALID_MEMORY_TYPES else "identity")


def _validate_memory_obj(mem: Any) -> Optional[dict]:
    """Return sanitized memory object or None."""
    if not isinstance(mem, dict):
        return None

    mtype = _normalize_memory_type(mem.get("memory_type") or mem.get("type"))
    key = _clean_key(mem.get("key") or "")
    value = str(mem.get("value") or "").strip()
    summary = str(mem.get("summary") or value).strip()
    try:
        confidence = int(mem.get("confidence", 85))
    except Exception:
        confidence = 85
    try:
        priority = int(mem.get("priority", 5))
    except Exception:
        priority = 5
    overwrite = bool(mem.get("overwrite", True))

    if not key or not value:
        return None
    if len(key) > 40:
        key = key[:40].rstrip()
    if len(value) > 500:
        value = value[:500].rstrip() + "…"
    if len(summary) > 200:
        summary = summary[:200].rstrip() + "…"
    confidence = max(0, min(confidence, 100))
    priority = max(1, min(priority, 10))

    return {
        "memory_type": mtype,
        "type": mtype,
        "key": key,
        "value": value,
        "summary": summary,
        "confidence": confidence,
        "priority": priority,
        "overwrite": overwrite,
    }


def _validate_learning_insight(item: Any) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    validated = _validate_memory_obj(item)
    if not validated:
        return None
    return {
        "memory_type": validated["memory_type"],
        "key": validated["key"],
        "value": validated["value"],
        "summary": validated["summary"],
        "confidence": validated["confidence"],
        "priority": validated["priority"],
        "overwrite": bool(item.get("overwrite") or item.get("override", False)),
        "evidence": str(item.get("evidence") or "").strip()[:240],
    }


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
  {
    "memory_type": "identity"|"preference"|"project"|"behavioral"|"relational"|"temporal"|"strategic",
    "key": קצר וברור (<=40 תווים),
    "value": טקסט קצר,
    "summary": סיכום קצר,
    "confidence": 0-100,
    "priority": 1-10,
    "overwrite": true|false
  }
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
  "memory_to_write": { "memory_type": "...", "key": "...", "value": "...", "summary": "...", "confidence": 0-100, "priority": 1-10, "overwrite": true|false } | null
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

MEMORY_LEARNING_SYSTEM_PROMPT = """
You are Benjamin's Memory Learning Engine.
Your job: inspect a user's message plus known context and decide whether we learned anything durable or strategically useful about Matan.

Return ONLY valid JSON with this schema:
{
  "learned_anything": true|false,
  "insights": [
    {
      "memory_type": "identity"|"preference"|"project"|"behavioral"|"relational"|"temporal"|"strategic",
      "key": "<short stable key <=40 chars>",
      "value": "<compressed insight>",
      "summary": "<one-line why it matters>",
      "confidence": 0-100,
      "priority": 1-10,
      "overwrite": true|false,
      "evidence": "<brief quote or rationale>"
    }
  ]
}

Rules:
- Extract at most 4 insights.
- Only store information that is durable, recurring, emotionally meaningful, or strategically relevant.
- Ignore trivial temporary states unless they represent a meaningful recent change worth temporal memory.
- Prefer compressed operator-grade wording over verbose restatement.
- Avoid duplicates if the known context already contains the same insight.
- Use relational memory for people / dating / emotional relationship context.
- Use behavioral memory for patterns, loops, strengths, blind spots, recurring mistakes, and execution issues.
- Use temporal memory for recent phase shifts, new blockers, current transitions, or meaningful updates likely to matter soon.
- Use preference memory for style, likes, dislikes, communication expectations.
- If the message contains a structured goal of any kind, preserve the concrete numbers, currency, role, name or status. Use stable keys per topic:
  * Fitness:  fitness_goal, current_weight_kg, target_weight_kg, goal_type (muscle_gain|fat_loss|recomp), fitness_status.
  * Finance:  finance_savings_goal, finance_income_goal, finance_investment_goal, finance_currency, finance_status.
  * Career:   career_target_role, career_recent_change, career_transition.
  * Business: business_revenue_goal, business_customer_target, business_launch_intent, business_status.
  * Learning: learning_focus, learning_status.
  * Habits:   active_habit, sleep_hours_goal.
  * Relationship: active_dating_status, ex_dynamic_active, recent_relationship_event.
  * Lifestyle: planned_relocation, planned_trip.
  * Health:   nutrition_focus, health_medical_event.
  Examples:
    "I'm starting training for mass gain. From 71kg to 76kg" -> fitness_goal, current_weight_kg=71, target_weight_kg=76, goal_type=muscle_gain.
    "אני רוצה להגיע למשכורת של 30k בחודש" -> finance_income_goal=30,000 ₪/month.
    "המטרה שלי לחסוך 200k שנה הקרובה" -> finance_savings_goal=200,000 ₪.
    "אני רוצה להיות Head of AI" -> career_target_role="Head of AI".
    "אני רוצה להגיע ל-10k MRR" -> business_revenue_goal=10,000 USD MRR.
    "אני מתחיל ללמוד ספרדית" -> learning_focus="Spanish".
    "אני מתחיל לישון 8 שעות בלילה" -> sleep_hours_goal=8.
- Be conservative. If nothing useful was learned, return learned_anything=false with an empty insights array.
""".strip()


def _build_user_prompt(message: str, memory_context: Optional[dict]) -> str:
    mc = memory_context or {}
    user_profile = mc.get("user_profile")
    relevant_memories = mc.get("relevant_memories") or []
    project_state = mc.get("project_state")
    retrieval_summary = mc.get("retrieval_summary") or {}

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
    user_brief = mc.get("user_brief")
    if user_brief:
        lines.append("USER_BRIEF: " + _clip(user_brief, 500))
    if retrieval_summary:
        lines.append("RETRIEVAL_SUMMARY: " + _clip(retrieval_summary, 500))

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
        """Backward-compatible wrapper around layered learning."""
        learned = await self.extract_memory_insights(message)
        insights = learned.get("insights") or []
        if not insights:
            return {"should_update": False}
        first = insights[0]
        return {
            "should_update": True,
            "field": str(first.get("key") or "")[:40],
            "value": str(first.get("value") or "")[:300],
            "override": bool(first.get("overwrite", False)),
            "confidence": int(first.get("confidence", 0)),
        }

    async def extract_memory_insights(self, message: str, memory_context: Optional[dict] = None) -> dict:
        known_context = {
            "user_brief": (memory_context or {}).get("user_brief") or {},
            "retrieval_summary": (memory_context or {}).get("retrieval_summary") or {},
            "relevant_memories": [
                {
                    "type": item.get("type"),
                    "key": item.get("key"),
                    "value": item.get("value"),
                }
                for item in ((memory_context or {}).get("relevant_memories") or [])[:10]
                if isinstance(item, dict)
            ],
        }
        payload = json.dumps(
            {
                "message": message,
                "known_context": known_context,
            },
            ensure_ascii=False,
        )
        resp = await self.client.chat.completions.create(
            model=MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": MEMORY_LEARNING_SYSTEM_PROMPT},
                {"role": "user", "content": payload},
            ],
        )

        text = (resp.choices[0].message.content or "").strip()
        out = _safe_json_loads(text) or {}
        insights_raw = out.get("insights") if isinstance(out.get("insights"), list) else []
        insights: list[dict] = []
        for item in insights_raw[:4]:
            validated = _validate_learning_insight(item)
            if not validated:
                continue
            if int(validated.get("confidence", 0)) < 70:
                continue
            insights.append(validated)
        return {
            "learned_anything": bool(insights),
            "insights": insights,
        }
