"""Message handler - routing, approval flow, kill switch, memory."""
import re
from collections import deque

from memory.memory_store import (
    add_memory,
    get_all_memories,
    get_profile,
    get_project_state,
    search_memories,
)
from orchestrator.benjamin_orchestrator import BenjaminOrchestrator

KILL_PHRASES = {"עצור", "stop"}
APPROVE_PHRASES = {"כן", "yes", "אשר"}
REJECT_PHRASES = {"לא", "no", "בטל"}

REMEMBER_PREFIXES = ("תזכור", "תזכרי", "remember")
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
    memories = search_memories(user_id, message, limit=8)
    project_state = get_project_state(user_id)
    return {
        "user_profile": profile,
        "relevant_memories": memories,
        "project_state": project_state,
    }


def _persist_memory(user_id: str, plan: dict, message: str) -> None:
    """Persist memory when plan suggests it and user approved."""
    mem = plan.get("memory_to_write")
    if mem and isinstance(mem, dict):
        mtype = mem.get("type", "fact")
        key = mem.get("key", "auto")
        value = mem.get("value", message[:500])
        add_memory(user_id, mtype, key, value)
        print(f"Memory saved: {key}={value[:50]}...")
    elif plan.get("suggest_memory_write"):
        add_memory(user_id, "fact", "auto", message[:500])
        print(f"Memory saved (auto): {message[:50]}...")


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

        # Explicit "מה אתה זוכר עליי"
        if normalized in RECALL_PHRASES:
            return self._format_recall_response(user_id)

        # Explicit "תזכור: ..." — save without approval
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
                f"level {plan['suggested_automation_level']}"
            )
            return self.orchestrator.format_approval_request(plan)

        return await self._execute_and_handle(
            user_id, message, plan, None, memory_context,
        )

    def _format_recall_response(self, user_id: str) -> str:
        """Return short list of stored facts/projects."""
        memories = get_all_memories(user_id, limit=15)
        profile = get_profile(user_id)
        state = get_project_state(user_id)

        lines = []
        if profile:
            lines.append("פרופיל: " + str(profile)[:200])
        for m in memories:
            lines.append(f"• {m.get('key', '')}: {str(m.get('value', ''))[:80]}")
        if state:
            lines.append("פרויקט: " + str(state)[:150])
        if not lines:
            return "עדיין לא שמרתי מידע עליך. תגיד 'תזכור: ...' כדי שאשמור."
        return "מה שאני זוכר:\n" + "\n".join(lines)

    async def _handle_explicit_remember(self, user_id: str, message: str) -> str:
        """Parse 'תזכור: X' and save as memory without approval."""
        for prefix in REMEMBER_PREFIXES:
            if message.lower().startswith(prefix):
                rest = message[len(prefix) :].strip()
                rest = rest.lstrip(": \t")
                if not rest:
                    return "מה לשמור? כתוב: תזכור: [המידע]"
                key = rest[:50].replace(" ", "_") or "fact"
                add_memory(user_id, "fact", key, rest)
                print(f"Explicit memory saved: {key}")
                return f"שמרתי: {rest[:80]}{'...' if len(rest) > 80 else ''}"
        return "מה לשמור?"

    async def _handle_approval(self, normalized: str, user_id: str) -> str:
        pending = self.pending_plans[user_id]
        original_message = pending["message"]
        plan = pending["plan"]
        memory_context = pending.get("memory_context", _load_memory_context(user_id, original_message))
        resume_state = pending.get("resume_state")

        # Approve
        if normalized in APPROVE_PHRASES:
            del self.pending_plans[user_id]
            print(
                f"User {user_id} approved "
                f"level {plan['suggested_automation_level']}"
            )
            return await self._execute_and_handle(
                user_id, original_message, plan, resume_state, memory_context,
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
                return "רמה לא תקינה (0-5). נסה שוב, או שלח 'לא' לביטול."

            plan["suggested_automation_level"] = new_level
            plan["execution_mode"] = (
                "agent_loop" if new_level >= 3 else "direct"
            )
            pending.pop("resume_state", None)
            print(f"User {user_id} changed level to {new_level}")

            if new_level <= 1:
                del self.pending_plans[user_id]
                return await self._execute_and_handle(
                    user_id, original_message, plan, None, memory_context,
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
        """Execute plan, handle mid-loop escalation, inject memory."""
        exec_context: dict = {
            "cancelled": False,
            "memory_context": memory_context,
        }
        self.active_contexts[user_id] = exec_context
        try:
            result = await self.orchestrator.execute(
                message, plan, exec_context, resume_state,
            )

            if isinstance(result, dict) and result.get("needs_approval"):
                self.pending_plans[user_id] = {
                    "message": message,
                    "plan": result["proposed_plan"],
                    "resume_state": result.get("resume_state"),
                    "memory_context": memory_context,
                }
                return result["approval_request_text"]

            if plan.get("suggest_memory_write"):
                _persist_memory(user_id, plan, message)
            self._store_context(user_id, message, result)
            return result
        finally:
            self.active_contexts.pop(user_id, None)

    def _store_context(self, user_id: str, message: str, response: str) -> None:
        if user_id not in self.context:
            self.context[user_id] = deque(maxlen=3)
        self.context[user_id].append(f"User: {message}\nAssistant: {response}")
