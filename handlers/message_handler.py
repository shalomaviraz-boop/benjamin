"""Message handler - routing, approval flow, kill switch, memory."""
from __future__ import annotations

import json
import re
import sqlite3
from collections import deque
from pathlib import Path

from memory.memory_store import (
    delete_memories_by_key,
    get_personal_model,
    get_profile,
    get_project_state,
    list_memories,
    search_memories,
    update_personal_model_field,
    upsert_memory,
    upsert_personal_model,
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
SHOW_MODEL_PHRASES = {"הצג מודל אישי", "show personal model"}
UPDATE_MODEL_PREFIXES = ("עדכן מודל אישי", "update personal model")
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
            "SELECT role, content FROM conversation_messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    rows.reverse()
    return [{"role": r[0], "content": r[1]} for r in rows]


def _build_user_brief(personal_model: dict) -> str:
    if not isinstance(personal_model, dict) or not personal_model:
        return ""
    lines = []
    if personal_model.get("name"):
        lines.append(f"שם: {personal_model['name']}")
    if personal_model.get("communication_style"):
        lines.append(f"סגנון: {personal_model['communication_style']}")
    if personal_model.get("current_main_mission"):
        lines.append(f"מטרה: {personal_model['current_main_mission']}")
    fitness_goal = personal_model.get("fitness_goal") or {}
    if isinstance(fitness_goal, dict) and fitness_goal:
        current = fitness_goal.get("current_weight")
        target = fitness_goal.get("target_weight")
        goal_type = fitness_goal.get("goal_type")
        if current or target or goal_type:
            lines.append(f"כושר: יעד {goal_type or ''}, משקל {current or '?'} -> {target or '?'}")
    return "\n".join(lines)


def _extract_structured_learning(message: str) -> dict:
    raw = (message or "").strip()
    lowered = raw.lower()
    model_updates: dict = {}
    memories: list[dict] = []

    name_match = re.search(r"(?:קוראים\s+לי|שמי)\s+([\u0590-\u05FFA-Za-z]+)", raw)
    if name_match:
        model_updates["name"] = name_match.group(1).strip()

    if any(k in lowered for k in ["תשובות קצרות", "תשובה קצרה", "בלי חפירות", "short answers"]):
        model_updates["communication_style"] = "קצר, חד, בלי חפירות ובלי ניסוחים רובוטיים"

    if any(k in lowered for k in ["מסה", "להעלות במשקל", "לעלות במשקל", "לעלות במסה"]):
        nums = re.findall(r"\d{2,3}(?:\.\d+)?", raw)
        current_weight = int(float(nums[0])) if len(nums) >= 1 else None
        target_weight = int(float(nums[1])) if len(nums) >= 2 else None
        fitness_goal = {"goal_type": "muscle_gain", "status": "active"}
        if current_weight:
            fitness_goal["current_weight"] = current_weight
        if target_weight:
            fitness_goal["target_weight"] = target_weight
        model_updates["fitness_goal"] = fitness_goal
        if target_weight:
            memories.append({
                "type": "fitness_goal",
                "key": "weight_gain_goal",
                "value": f"מטרה פעילה: לעלות במסה מ-{current_weight or '?'} ל-{target_weight} קילו",
            })
    return {"model_updates": model_updates, "memories": memories}


def _load_memory_context(user_id: str, message: str) -> dict:
    profile = get_profile(user_id)
    personal_model = get_personal_model(user_id) or {}
    relevant_memories = search_memories(user_id, message, limit=8)
    recent_memories = list_memories(user_id, limit=10)
    project_state = get_project_state(user_id)
    conversation_tail = _get_tail(user_id, limit=15)
    return {
        "user_profile": profile,
        "personal_model": personal_model,
        "user_brief": _build_user_brief(personal_model),
        "relevant_memories": relevant_memories,
        "recent_memories": recent_memories,
        "project_state": project_state,
        "conversation_tail": conversation_tail,
    }


def _persist_memory(user_id: str, plan: dict) -> None:
    if not plan.get("suggest_memory_write"):
        return
    mem = plan.get("memory_to_write")
    if not mem or not isinstance(mem, dict):
        return
    mtype = (mem.get("type") or "fact").strip()
    key = (mem.get("key") or "").strip()
    value = (mem.get("value") or "").strip()
    if key and value:
        upsert_memory(user_id, mtype, key, value)


def _parse_remember_payload(message: str) -> dict | None:
    raw = message.strip()
    lower = raw.lower()
    prefix_used = None
    for p in REMEMBER_PREFIXES:
        if lower.startswith(p):
            prefix_used = p
            break
    if not prefix_used:
        return None
    rest = raw[len(prefix_used):].strip().lstrip(": ")
    if not rest:
        return None
    if "=" in rest:
        k, v = rest.split("=", 1)
        if k.strip() and v.strip():
            return {"type": "fact", "key": k.strip(), "value": v.strip()}
    if ":" in rest:
        k, v = rest.split(":", 1)
        if k.strip() and v.strip():
            return {"type": "fact", "key": k.strip(), "value": v.strip()}
    return {"type": "note", "key": "note", "value": rest}


def _parse_forget_key(message: str) -> str | None:
    raw = message.strip()
    if raw.startswith("שכח:"):
        return raw.split(":", 1)[1].strip() or None
    if raw.lower().startswith("forget:"):
        return raw.split(":", 1)[1].strip() or None
    return None


class BenjaminMessageHandler:
    def __init__(self):
        self.orchestrator = BenjaminOrchestrator()
        self.context: dict[str, deque] = {}
        self.pending_plans: dict[str, dict] = {}
        self.active_contexts: dict[str, dict] = {}

    async def handle(self, message: str, user_id: str) -> str:
        normalized = message.strip().lower()
        trimmed = message.strip()

        if normalized in KILL_PHRASES:
            self.pending_plans.pop(user_id, None)
            if user_id in self.active_contexts:
                self.active_contexts[user_id]["cancelled"] = True
            return "נעצר."

        forget_key = _parse_forget_key(trimmed)
        if forget_key:
            deleted = delete_memories_by_key(user_id, forget_key)
            return f"מחקתי: {forget_key} ({deleted})"

        if normalized in RECALL_PHRASES:
            return self._format_recall_response(user_id)

        if normalized in SHOW_MODEL_PHRASES:
            personal_model = get_personal_model(user_id) or {}
            if not personal_model:
                return "אין עדיין מודל אישי שמור."
            return "מודל אישי:\n" + json.dumps(personal_model, ensure_ascii=False, indent=2)

        for prefix in UPDATE_MODEL_PREFIXES:
            if trimmed.startswith(prefix):
                try:
                    json_part = trimmed[len(prefix):].strip().lstrip(": ")
                    data = json.loads(json_part)
                    if not isinstance(data, dict):
                        return "יש לספק JSON תקין כאובייקט."
                    upsert_personal_model(user_id, data)
                    return "המודל האישי עודכן."
                except Exception:
                    return "JSON לא תקין. כתוב: עדכן מודל אישי: { ... }"

        if trimmed.lower().startswith(REMEMBER_PREFIXES):
            return await self._handle_explicit_remember(user_id, trimmed)

        if user_id in self.pending_plans:
            return await self._handle_approval(normalized, user_id)

        memory_context = _load_memory_context(user_id, message)
        try:
            learned = _extract_structured_learning(message)
            for field, value in (learned.get("model_updates") or {}).items():
                update_personal_model_field(user_id, field, value)
            for mem in (learned.get("memories") or []):
                upsert_memory(user_id, mem["type"], mem["key"], mem["value"])
            if learned.get("model_updates"):
                memory_context = _load_memory_context(user_id, message)
        except Exception as e:
            print(f"Structured learning error: {e}")

        governor = await self.orchestrator.governor(message, memory_context)
        memory_context["governor"] = governor

        plan = await self.orchestrator.plan(message, memory_context)
        if self.orchestrator.needs_approval(plan, message):
            self.pending_plans[user_id] = {"message": message, "plan": plan, "memory_context": memory_context}
            return self.orchestrator.format_approval_request(plan)
        return await self._execute_and_handle(user_id, message, plan, None, memory_context)

    def _format_recall_response(self, user_id: str) -> str:
        personal_model = get_personal_model(user_id) or {}
        memories = list_memories(user_id, limit=10)
        lines = []
        if personal_model.get("name"):
            lines.append(f"שם: {personal_model['name']}")
        fitness_goal = personal_model.get("fitness_goal") or {}
        if isinstance(fitness_goal, dict) and fitness_goal.get("target_weight"):
            lines.append(f"כושר: לעלות מ-{fitness_goal.get('current_weight', '?')} ל-{fitness_goal['target_weight']} קילו")
        for m in memories[:6]:
            lines.append(f"• ({m.get('type')}) {m.get('key')}: {str(m.get('value', ''))[:80]}")
        return "עדיין לא שמרתי מידע עליך." if not lines else "מה שאני זוכר:\n" + "\n".join(lines)

    async def _handle_explicit_remember(self, user_id: str, message: str) -> str:
        payload = _parse_remember_payload(message)
        if not payload:
            return "מה לשמור? כתוב: תזכור: key=value"
        upsert_memory(user_id, payload["type"], payload["key"], payload["value"])
        learned = _extract_structured_learning(payload["value"])
        for field, value in (learned.get("model_updates") or {}).items():
            update_personal_model_field(user_id, field, value)
        for mem in (learned.get("memories") or []):
            upsert_memory(user_id, mem["type"], mem["key"], mem["value"])
        return "שמרתי."

    async def _handle_approval(self, normalized: str, user_id: str) -> str:
        pending = self.pending_plans[user_id]
        original_message = pending["message"]
        plan = pending["plan"]
        memory_context = pending.get("memory_context", _load_memory_context(user_id, original_message))
        resume_state = pending.get("resume_state")

        if normalized in APPROVE_PHRASES:
            del self.pending_plans[user_id]
            return await self._execute_and_handle(user_id, original_message, plan, resume_state, memory_context)
        if normalized in REJECT_PHRASES:
            del self.pending_plans[user_id]
            return "בוטל."
        level_match = re.search(r"(?:שנה\s*רמה|רמה)\s*(\d)", normalized)
        if not level_match and normalized.isdigit():
            level_match = re.match(r"(\d)", normalized)
        if level_match:
            new_level = int(level_match.group(1))
            if not 0 <= new_level <= 5:
                return "רמה לא תקינה (0-5)."
            plan["suggested_automation_level"] = new_level
            plan["execution_mode"] = "agent_loop" if new_level >= 3 else "direct"
            pending.pop("resume_state", None)
            if new_level <= 1:
                del self.pending_plans[user_id]
                return await self._execute_and_handle(user_id, original_message, plan, None, memory_context)
            self.pending_plans[user_id] = pending
            return self.orchestrator.format_approval_request(plan)
        del self.pending_plans[user_id]
        return "בוטל. שלח את הבקשה מחדש."

    async def _execute_and_handle(self, user_id: str, message: str, plan: dict, resume_state: dict | None, memory_context: dict | None) -> str:
        exec_context: dict = {"cancelled": False, "memory_context": memory_context, "user_id": user_id}
        self.active_contexts[user_id] = exec_context
        try:
            _save_turn(user_id, "user", message)
            result = await self.orchestrator.execute(message, plan, exec_context, resume_state)
            if isinstance(result, dict) and result.get("needs_approval"):
                self.pending_plans[user_id] = {
                    "message": message,
                    "plan": result["proposed_plan"],
                    "resume_state": result.get("resume_state"),
                    "memory_context": memory_context,
                }
                return result["approval_request_text"]
            _persist_memory(user_id, plan)
            _save_turn(user_id, "assistant", result)
            return result
        finally:
            self.active_contexts.pop(user_id, None)
