"""Message handler - routing, approval flow, kill switch, memory."""
import re
from collections import deque
import sqlite3
from pathlib import Path

from memory.memory_store import (
    upsert_memory,
    list_memories,
    delete_memories_by_key,
    get_profile,
    get_project_state,
    search_memories,
    get_personal_model,
    upsert_personal_model,
    update_personal_model_field,
    build_user_brief,
    extract_rule_based_memory_insights,
    load_memory_context_snapshot,
    learn_from_interaction,
    seed_user_core_profile,
)
from orchestrator.benjamin_orchestrator import BenjaminOrchestrator

KILL_PHRASES = {"עצור", "stop"}
APPROVE_PHRASES = {"כן", "yes", "אשר"}
REJECT_PHRASES = {"לא", "no", "בטל"}

REMEMBER_PREFIXES = ("תזכור", "תזכרי", "remember")
FORGET_PREFIXES = ("שכח", "forget")

RECALL_PHRASES = {
    "מה אתה זוכר עליי",
    "מה את זוכרת עליי",
    "מה אתה זוכר עלי",
    "מה את זוכרת עלי",
    "what do you remember about me",
}

SHOW_MODEL_PHRASES = {"הצג מודל אישי", "show personal model"}
UPDATE_MODEL_PREFIXES = ("עדכן מודל אישי", "update personal model")
IMPLICIT_MEMORY_PREFIXES = ("חשוב שתדע ש", "חשוב שתדעי ש", "המטרה שלי היא", "my goal is")

# --- Conversation SQLite setup ---
_DB_PATH = Path(__file__).resolve().parent.parent / "conversation.db"


def _get_conn():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return conn


def _save_turn(user_id: str, role: str, content: str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO conversation_messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )
        conn.commit()
    finally:
        conn.close()


def _get_tail(user_id: str, limit: int = 15) -> list[dict]:
    conn = _get_conn()
    try:
        cur = conn.execute(
            """
            SELECT role, content
            FROM conversation_messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    rows.reverse()
    return [{"role": r[0], "content": r[1]} for r in rows]


def _coerce_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


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


def _build_user_brief(
    profile: dict | None,
    personal_model: dict,
    recent_memories: list[dict],
    project_state: dict | None,
    **kwargs,
) -> dict:
    return build_user_brief(profile, personal_model, recent_memories, project_state, **kwargs)


def _load_memory_context(user_id: str, message: str) -> dict:
    """Load user profile + relevant memories + project state for prompts."""
    conversation_tail = _get_tail(user_id, limit=15)
    return load_memory_context_snapshot(
        user_id,
        message,
        conversation_tail=conversation_tail,
    )


def _persist_memory(user_id: str, plan: dict) -> None:
    """
    Persist memory only when plan suggests it AND user approved (handled by orchestrator gate).
    Expects plan["memory_to_write"] to be structured dict or None.
    """
    if not plan.get("suggest_memory_write"):
        return

    mem = plan.get("memory_to_write")
    if not mem or not isinstance(mem, dict):
        return

    mtype = (mem.get("memory_type") or mem.get("type") or "identity").strip()
    key = (mem.get("key") or "").strip()
    value = (mem.get("value") or "").strip()

    if not key or not value:
        return

    learned = learn_from_interaction(
        user_id,
        f"plan_memory:{key}",
        [
            {
                "memory_type": mtype,
                "key": key,
                "value": value,
                "summary": mem.get("summary") or value,
                "confidence": mem.get("confidence", 85),
                "priority": mem.get("priority", 5),
                "overwrite": mem.get("overwrite", True),
            }
        ],
        source="plan_memory_write",
    )
    if learned:
        print(f"Memory saved: ({mtype}) {key}={value[:50]}...")


def _should_run_learning(message: str) -> bool:
    text = (message or "").strip()
    if len(text) < 12:
        return False
    lowered = text.lower()
    if lowered.startswith(REMEMBER_PREFIXES) or lowered.startswith(FORGET_PREFIXES):
        return False
    if lowered in RECALL_PHRASES or lowered in SHOW_MODEL_PHRASES:
        return False
    return True


def _looks_like_contextual_remember(message: str) -> bool:
    normalized = (message or "").strip().lower()
    return bool(re.fullmatch(r"(תזכור|תזכרי|remember)(:)?\s*(את זה|זה|this)?", normalized))


def _get_last_meaningful_context(user_id: str) -> str:
    for item in reversed(_get_tail(user_id, limit=8)):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if content and not _looks_like_contextual_remember(content):
            return content
    return ""


_GOAL_TOPIC_SPECS: list[dict] = [
    {
        "name": "fitness",
        "trigger_terms": ("כושר", "fitness", "מסה", "bulk", "muscle", "משקל", "אימון", "training"),
        "search_query": "fitness goal mass current target weight muscle bulk כושר מסה משקל",
        "primary_key": "fitness_goal",
        "label_he": "מטרת הכושר שלך",
        "render": "fitness",
    },
    {
        "name": "business_revenue",
        "trigger_terms": ("עסק", "business", "mrr", "arr", "revenue", "הכנסה עסקית", "saas"),
        "must_terms": ("עסק", "business", "mrr", "arr", "saas", "revenue"),
        "search_query": "business revenue mrr arr עסק הכנסה",
        "primary_key": "business_revenue_goal",
        "label_he": "יעד ההכנסה העסקית שלך",
    },
    {
        "name": "business_customers",
        "trigger_terms": ("לקוחות", "customers", "users", "משתמשים"),
        "search_query": "business customers users לקוחות משתמשים",
        "primary_key": "business_customer_target",
        "label_he": "יעד הלקוחות שלך",
    },
    {
        "name": "finance_savings",
        "trigger_terms": ("חיסכון", "savings", "לחסוך", "save"),
        "search_query": "finance savings goal חיסכון לחסוך",
        "primary_key": "finance_savings_goal",
        "label_he": "יעד החיסכון שלך",
    },
    {
        "name": "finance_income",
        "trigger_terms": ("הכנסה", "income", "salary", "משכורת", "להרוויח", "earn"),
        "search_query": "finance income salary goal הכנסה משכורת להרוויח",
        "primary_key": "finance_income_goal",
        "label_he": "יעד ההכנסה שלך",
    },
    {
        "name": "finance_investment",
        "trigger_terms": ("השקעה", "invest", "portfolio", "תיק"),
        "search_query": "finance investment portfolio השקעה תיק",
        "primary_key": "finance_investment_goal",
        "label_he": "יעד ההשקעה שלך",
    },
    {
        "name": "career",
        "trigger_terms": ("קריירה", "career", "תפקיד", "role", "job", "עבודה"),
        "search_query": "career role target job קריירה תפקיד עבודה",
        "primary_key": "career_target_role",
        "label_he": "יעד הקריירה שלך",
    },
    {
        "name": "learning",
        "trigger_terms": ("ללמוד", "learn", "course", "קורס", "study", "לימוד"),
        "search_query": "learning study course skill ללמוד קורס לימוד",
        "primary_key": "learning_focus",
        "label_he": "פוקוס הלימוד שלך",
    },
    {
        "name": "sleep",
        "trigger_terms": ("שינה", "sleep", "לישון"),
        "search_query": "sleep hours שינה שעות",
        "primary_key": "sleep_hours_goal",
        "label_he": "יעד השינה שלך",
    },
    {
        "name": "habit",
        "trigger_terms": ("הרגל", "habit", "routine", "שגרה"),
        "search_query": "habit routine daily הרגל שגרה",
        "primary_key": "active_habit",
        "label_he": "ההרגל הפעיל שלך",
    },
    {
        "name": "primary_goal",
        "trigger_terms": ("המטרה הראשית", "main goal", "primary goal", "המטרה שלי"),
        "search_query": "primary goal stated_primary_goal",
        "primary_key": "stated_primary_goal",
        "label_he": "המטרה שהצהרת עליה",
    },
]


def _format_goal_answer(spec: dict, primary: str, values: dict) -> str:
    if spec.get("render") == "fitness":
        current = values.get("current_weight_kg")
        target = values.get("target_weight_kg")
        if current and target:
            return f"מטרת הכושר שלך כרגע היא לעלות מ-{current} ל-{target} ק\"ג."
        return primary
    label = spec["label_he"]
    cleaned = re.sub(r"^(יעד|מטרת|פוקוס|הרגל)\s+\S+(?:\s+\S+)?\s*:\s*", "", primary).strip()
    if not cleaned:
        cleaned = primary
    return f"{label}: {cleaned}"


def _try_answer_goal_query(user_id: str, message: str) -> str | None:
    lowered = (message or "").lower()
    goal_terms = ("מטרה", "יעד", "goal", "target", "what's my", "מה ה", "מה ה-")
    if not any(term in lowered for term in goal_terms):
        return None

    for spec in _GOAL_TOPIC_SPECS:
        if not any(term in lowered for term in spec["trigger_terms"]):
            continue
        must = spec.get("must_terms")
        if must and not any(term in lowered for term in must):
            continue
        matches = search_memories(user_id, spec["search_query"], limit=12)
        values = {str(item.get("key") or ""): str(item.get("value") or "") for item in matches}
        primary = values.get(spec["primary_key"])
        if not primary:
            continue
        return _format_goal_answer(spec, primary, values)
    return None


def _parse_remember_payload(message: str) -> dict | None:
    """
    Supports:
      תזכור: key = value
      תזכור: key: value
    Else:
      type="note", key="note", value=<text>
    Returns dict: {type, key, value} or None.
    """
    raw = message.strip()

    # Special-case: user name (e.g., "תזכור שקוראים לי מתן")
    name_match = re.search(r"(?:קוראים\s+לי|שמי)\s+([\u0590-\u05FFA-Za-z]+)", raw)
    if name_match:
        name = name_match.group(1).strip()
        if name:
            return {"type": "profile", "key": "name", "value": name}

    name_match_en = re.search(r"\bmy\s+name\s+is\s+([A-Za-z]+)\b", raw, re.IGNORECASE)
    if name_match_en:
        name = name_match_en.group(1).strip()
        if name:
            return {"type": "profile", "key": "name", "value": name}

    # strip prefix
    lower = raw.lower()
    prefix_used = None
    for p in REMEMBER_PREFIXES:
        if lower.startswith(p):
            prefix_used = p
            break
    if not prefix_used:
        return None

    rest = raw[len(prefix_used):].strip()
    rest = rest.lstrip(": \t")
    if not rest:
        return None

    # key = value
    if "=" in rest:
        k, v = rest.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k and v:
            return {"type": "fact", "key": k, "value": v}

    # key: value
    if ":" in rest:
        k, v = rest.split(":", 1)
        k = k.strip()
        v = v.strip()
        if k and v:
            return {"type": "fact", "key": k, "value": v}

    # direct goal phrasing
    if rest.startswith("שאני"):
        value = rest[4:].strip()
        if value:
            return {"type": "identity", "key": "important_user_fact", "value": value}
    if rest.startswith("I am"):
        value = rest[4:].strip()
        if value:
            return {"type": "identity", "key": "important_user_fact", "value": value}

    # fallback note
    return {"type": "note", "key": "note", "value": rest}


def _parse_forget_key(message: str) -> str | None:
    """
    Supports:
      שכח: key
      forget: key
    Returns key or None.
    """
    raw = message.strip()
    lower = raw.lower()

    if raw.startswith("שכח:"):
        key = raw.split(":", 1)[1].strip()
        return key or None

    if lower.startswith("forget:"):
        key = raw.split(":", 1)[1].strip()
        return key or None

    return None


class BenjaminMessageHandler:
    """Handles incoming messages with context, approval gates, kill switch, memory."""

    def __init__(self):
        self.orchestrator = BenjaminOrchestrator()
        self.context: dict[str, deque] = {}
        self.pending_plans: dict[str, dict] = {}
        self.active_contexts: dict[str, dict] = {}

    async def handle(self, message: str, user_id: str) -> str:
        normalized = message.strip().lower()
        trimmed = message.strip()
        seed_user_core_profile(user_id)

        # Kill switch
        if normalized in KILL_PHRASES:
            self.pending_plans.pop(user_id, None)
            if user_id in self.active_contexts:
                self.active_contexts[user_id]["cancelled"] = True
            print(f"Kill switch activated by {user_id}")
            return "נעצר."

        # Forget command
        forget_key = _parse_forget_key(trimmed)
        if forget_key:
            deleted = delete_memories_by_key(user_id, forget_key)
            return f"מחקתי: {forget_key} ({deleted})"
        if trimmed.startswith("שכח:") or normalized.startswith("forget:"):
            return "מה למחוק? כתוב: שכח: key"

        # Recall memories
        if normalized in RECALL_PHRASES:
            return self._format_recall_response(user_id)

        direct_goal_answer = _try_answer_goal_query(user_id, trimmed)
        if direct_goal_answer:
            return direct_goal_answer

        # Show personal model
        if normalized in SHOW_MODEL_PHRASES:
            personal_model = get_personal_model(user_id) or {}
            if not personal_model:
                return "אין עדיין מודל אישי שמור."
            return "מודל אישי:\n" + str(personal_model)

        # Update personal model (JSON expected after prefix)
        for prefix in UPDATE_MODEL_PREFIXES:
            if trimmed.startswith(prefix):
                try:
                    import json
                    json_part = trimmed[len(prefix):].strip()
                    if json_part.startswith(":"):
                        json_part = json_part[1:].strip()
                    data = json.loads(json_part)
                    if not isinstance(data, dict):
                        return "יש לספק JSON תקין כאובייקט."
                    upsert_personal_model(user_id, data)
                    return "המודל האישי עודכן."
                except Exception:
                    return "JSON לא תקין. כתוב: עדכן מודל אישי: { ... }"

        # Explicit remember (no approval)
        if trimmed.lower().startswith(REMEMBER_PREFIXES):
            return await self._handle_explicit_remember(user_id, trimmed)

        # Pending approval (initial or mid-loop escalation)
        if user_id in self.pending_plans:
            return await self._handle_approval(normalized, user_id)

        # Normal flow: load memory
        memory_context = _load_memory_context(user_id, message)

        # --- Auto Learning: multi-layer memory extraction ---
        try:
            if _should_run_learning(message):
                extracted = await self.orchestrator.router.extract_memory_insights(
                    message,
                    memory_context=memory_context,
                )
                insights = extracted.get("insights") if isinstance(extracted, dict) else []
                deterministic = extract_rule_based_memory_insights(
                    message,
                    conversation_tail=memory_context.get("conversation_tail") or [],
                )
                learned = learn_from_interaction(
                    user_id,
                    message,
                    deterministic + (insights if isinstance(insights, list) else []),
                    source="message_learning",
                )
                if learned:
                    memory_context = _load_memory_context(user_id, message)
                    print(f"Auto-learned {len(learned)} memory insight(s)")
        except Exception as e:
            print(f"Profile extractor error: {e}")

        # --- Governor (after personal model update) ---
        governor = await self.orchestrator.governor(message, memory_context)
        memory_context["governor"] = governor

        plan = await self.orchestrator.plan(message, memory_context)

        if self.orchestrator.needs_approval(plan, message):
            self.pending_plans[user_id] = {
                "message": message,
                "plan": plan,
                "memory_context": memory_context,
            }
            print(
                f"Approval requested for user {user_id}: "
                f"level {plan.get('suggested_automation_level')}"
            )
            return self.orchestrator.format_approval_request(plan)

        return await self._execute_and_handle(
            user_id, message, plan, None, memory_context
        )

    def _format_recall_response(self, user_id: str) -> str:
        memory_context = _load_memory_context(user_id, "what do you remember about me")
        memories = memory_context.get("relevant_memories") or []
        profile = memory_context.get("user_profile")
        state = memory_context.get("project_state")
        personal_model = memory_context.get("personal_model") or {}
        memory_layers = memory_context.get("memory_layers") or {}
        user_brief = _build_user_brief(
            profile,
            personal_model,
            memory_context.get("recent_memories") or [],
            state,
            memory_layers=memory_layers,
        )

        lines: list[str] = []
        if user_brief:
            lines.append("תקציר אישי: " + str(user_brief)[:240])
        if profile:
            lines.append("פרופיל: " + str(profile)[:200])

        for layer_name, items in memory_layers.items():
            if not items:
                continue
            lines.append(f"{layer_name}:")
            for m in items[:3]:
                key = m.get("key", "")
                val = str(m.get("value", ""))[:90]
                lines.append(f"• {key}: {val}")

        if state:
            lines.append("פרויקט: " + str(state)[:150])

        if not lines:
            return "עדיין לא שמרתי מידע עליך. כתוב: תזכור: עיר=ראשון לציון"

        return "מה שאני זוכר:\n" + "\n".join(lines)

    async def _handle_explicit_remember(self, user_id: str, message: str) -> str:
        contextual_text = _get_last_meaningful_context(user_id) if _looks_like_contextual_remember(message) else ""
        payload = _parse_remember_payload(message)
        deterministic = extract_rule_based_memory_insights(
            contextual_text or message,
            conversation_tail=_get_tail(user_id, limit=8),
        )
        if not payload:
            if deterministic:
                learn_from_interaction(
                    user_id,
                    contextual_text or message,
                    deterministic,
                    source="explicit_remember",
                )
                return "שמרתי."
            return "שמרתי."

        mtype = payload["type"]
        key = payload["key"]
        value = payload["value"]
        manual_insights = list(deterministic)
        trivial_values = {"את זה", "זה", "this", "note"}
        if value.strip().lower() not in {item.lower() for item in trivial_values}:
            manual_insights.append(
                {
                    "memory_type": mtype,
                    "key": key,
                    "value": value,
                    "summary": value,
                    "confidence": 90,
                    "priority": 6,
                    "overwrite": True,
                }
            )
        elif not manual_insights:
            manual_insights.append(
                {
                    "memory_type": "temporal",
                    "key": "remember_request",
                    "value": contextual_text or "User asked Benjamin to remember recent context.",
                    "summary": "User explicitly asked Benjamin to remember something.",
                    "confidence": 72,
                    "priority": 4,
                    "overwrite": True,
                }
            )

        learn_from_interaction(
            user_id,
            contextual_text or message,
            manual_insights,
            source="explicit_remember",
        )
        return "שמרתי."

    async def _handle_approval(self, normalized: str, user_id: str) -> str:
        pending = self.pending_plans[user_id]
        original_message = pending["message"]
        plan = pending["plan"]
        memory_context = pending.get(
            "memory_context", _load_memory_context(user_id, original_message)
        )
        resume_state = pending.get("resume_state")

        # Approve
        if normalized in APPROVE_PHRASES:
            del self.pending_plans[user_id]
            print(
                f"User {user_id} approved level {plan.get('suggested_automation_level')}"
            )
            return await self._execute_and_handle(
                user_id, original_message, plan, resume_state, memory_context
            )

        # Reject
        if normalized in REJECT_PHRASES:
            del self.pending_plans[user_id]
            print(f"User {user_id} rejected plan")
            return "בוטל."

        # Level change
        level_match = re.search(r"(?:שנה\s*רמה|רמה)\s*(\d)", normalized)
        if not level_match and normalized.isdigit():
            level_match = re.match(r"(\d)", normalized)

        if level_match:
            new_level = int(level_match.group(1))
            if not 0 <= new_level <= 5:
                return "רמה לא תקינה (0-5)."

            plan["suggested_automation_level"] = new_level
            plan["execution_mode"] = "agent_loop" if new_level >= 3 else "direct"

            # changing level cancels resume state (fresh run)
            pending.pop("resume_state", None)
            print(f"User {user_id} changed level to {new_level}")

            if new_level <= 1:
                del self.pending_plans[user_id]
                return await self._execute_and_handle(
                    user_id, original_message, plan, None, memory_context
                )

            self.pending_plans[user_id] = pending
            return self.orchestrator.format_approval_request(plan)

        del self.pending_plans[user_id]
        return "בוטל. שלח את הבקשה מחדש."

    async def _execute_and_handle(
        self,
        user_id: str,
        message: str,
        plan: dict,
        resume_state: dict | None,
        memory_context: dict | None,
    ) -> str:
        exec_context: dict = {
            "cancelled": False,
            "memory_context": memory_context,
            "user_id": user_id,
        }
        self.active_contexts[user_id] = exec_context
        try:
            # Save user message
            _save_turn(user_id, "user", message)

            result = await self.orchestrator.execute(
                message, plan, exec_context, resume_state
            )

            # Mid-loop approval required
            if isinstance(result, dict) and result.get("needs_approval"):
                self.pending_plans[user_id] = {
                    "message": message,
                    "plan": result["proposed_plan"],
                    "resume_state": result.get("resume_state"),
                    "memory_context": memory_context,
                }
                return result["approval_request_text"]

            # Persist suggested memory only after successful execution + approval gate
            _persist_memory(user_id, plan)

            # Save assistant response
            _save_turn(user_id, "assistant", result)

            return result
        finally:
            self.active_contexts.pop(user_id, None)
