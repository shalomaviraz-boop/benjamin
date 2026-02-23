"""Message handler - routing, approval flow, kill switch, memory."""
import re
from collections import deque

from memory.memory_store import (
    upsert_memory,
    list_memories,
    delete_memories_by_key,
    get_profile,
    get_project_state,
    search_memories,
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


def _load_memory_context(user_id: str, message: str) -> dict:
    """Load user profile + relevant memories + project state for prompts."""
    profile = get_profile(user_id)
    relevant_memories = search_memories(user_id, message, limit=8)
    recent_memories = list_memories(user_id, limit=10)
    project_state = get_project_state(user_id)
    return {
        "user_profile": profile,
        "relevant_memories": relevant_memories,
        "recent_memories": recent_memories,
        "project_state": project_state,
    }


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

    mtype = (mem.get("type") or "fact").strip()
    key = (mem.get("key") or "").strip()
    value = (mem.get("value") or "").strip()

    if not key or not value:
        return

    upsert_memory(user_id, mtype, key, value)
    print(f"Memory saved: ({mtype}) {key}={value[:50]}...")


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

        # Explicit remember (no approval)
        if trimmed.lower().startswith(REMEMBER_PREFIXES):
            return await self._handle_explicit_remember(user_id, trimmed)

        # Pending approval (initial or mid-loop escalation)
        if user_id in self.pending_plans:
            return await self._handle_approval(normalized, user_id)

        # Normal flow: load memory, plan, execute
        memory_context = _load_memory_context(user_id, message)
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
        memories = list_memories(user_id, limit=15)
        profile = get_profile(user_id)
        state = get_project_state(user_id)

        lines: list[str] = []
        if profile:
            lines.append("פרופיל: " + str(profile)[:200])

        for m in memories:
            mtype = m.get("type", "")
            key = m.get("key", "")
            val = str(m.get("value", ""))[:80]
            lines.append(f"• ({mtype}) {key}: {val}")

        if state:
            lines.append("פרויקט: " + str(state)[:150])

        if not lines:
            return "עדיין לא שמרתי מידע עליך. כתוב: תזכור: עיר=ראשון לציון"

        return "מה שאני זוכר:\n" + "\n".join(lines)

    async def _handle_explicit_remember(self, user_id: str, message: str) -> str:
        payload = _parse_remember_payload(message)
        if not payload:
            return "מה לשמור? כתוב: תזכור: key=value"

        mtype = payload["type"]
        key = payload["key"]
        value = payload["value"]

        upsert_memory(user_id, mtype, key, value)
        return f"שמרתי.\n(type={mtype}, key={key}, value={value[:120]})"

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
        }
        self.active_contexts[user_id] = exec_context
        try:
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

            self._store_context(user_id, message, result)
            return result
        finally:
            self.active_contexts.pop(user_id, None)

    def _store_context(self, user_id: str, message: str, response: str) -> None:
        if user_id not in self.context:
            self.context[user_id] = deque(maxlen=3)
        self.context[user_id].append(f"User: {message}\nAssistant: {response}")