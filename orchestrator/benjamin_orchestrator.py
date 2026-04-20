"""Benjamin orchestrator: routing, execution, and validation."""
from __future__ import annotations

import time
from typing import Any

from agents.registry import registry as agent_registry
from agents.agent_contract import normalize_agent_result
from experts.claude_client import review_and_improve_code, sanity_check_answer
from experts.gpt_orchestrator import GPTOrchestrator
from experts.model_router import ModelRouter
from orchestrator.validation_layer import ValidationLayer
from utils.logger import log_orchestration

try:
    from orchestrator.hybrid_router import HybridRouter
except Exception:  # pragma: no cover
    HybridRouter = None

try:
    from orchestrator.agent_loop import run_agent_loop
except Exception:  # pragma: no cover
    run_agent_loop = None

TASK_AGENT_MAP = {
    "research": "research",
    "memory": "memory",
    "planning": "planning",
    "execution": "execution",
    "verification": "verification",
    "code": "code",
    "finance": "finance",
    "assistant": "assistant",
    "fitness_health": "fitness_health",
    "relationships": "relationships",
    "business_strategy": "business_strategy",
    "ai_expert": "ai_expert",
    # personal_synthesis is handled directly in the model router, no specialized agent.
}


def _bool(v: Any, default: bool = False) -> bool:
    return v if isinstance(v, bool) else default


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _normalize_plan(plan: dict | None) -> dict:
    plan = dict(plan or {})
    plan.setdefault("suggested_automation_level", 0)
    plan.setdefault("execution_mode", "direct")
    plan.setdefault("tools_required", [])
    plan.setdefault("use_web", False)
    plan.setdefault("grounded_web", False)
    plan.setdefault("require_verification", False)
    plan.setdefault("require_code_review", False)
    plan.setdefault("require_task_decomposition", False)
    plan.setdefault("governors", {})
    plan.setdefault("reason", "")
    plan.setdefault("suggest_memory_write", False)
    plan.setdefault("memory_to_write", None)
    plan.setdefault("task_type", None)
    plan.setdefault("routing_source", None)
    plan["suggested_automation_level"] = max(0, min(5, _int(plan["suggested_automation_level"], 0)))
    if plan["execution_mode"] not in {"direct", "agent_loop"}:
        plan["execution_mode"] = "agent_loop" if plan["suggested_automation_level"] >= 3 else "direct"
    plan["use_web"] = _bool(plan["use_web"])
    plan["grounded_web"] = _bool(plan["grounded_web"])
    # When we've already marked the answer as grounded on the live web,
    # don't let a non-web model overwrite it with stale cutoff knowledge.
    if plan["grounded_web"]:
        plan["use_web"] = True
        plan["require_verification"] = False
        plan["require_code_review"] = False
    plan["require_verification"] = _bool(plan["require_verification"])
    plan["require_code_review"] = _bool(plan["require_code_review"])
    plan["require_task_decomposition"] = _bool(plan["require_task_decomposition"])
    plan["suggest_memory_write"] = _bool(plan["suggest_memory_write"])
    if not isinstance(plan["tools_required"], list):
        plan["tools_required"] = []
    if not isinstance(plan["governors"], dict):
        plan["governors"] = {}
    return plan


class BenjaminOrchestrator:
    def __init__(self):
        self.gpt_router = GPTOrchestrator()
        self.router = HybridRouter(self.gpt_router) if HybridRouter is not None else self.gpt_router
        self.agent_registry = agent_registry
        self.validation_layer = ValidationLayer()
        self.model_router = ModelRouter()

    async def plan(self, message: str, memory_context: dict | None = None) -> dict:
        plan = await self.router.decide(message, memory_context=memory_context)
        plan = _normalize_plan(plan)
        plan.setdefault("task_type", self._resolve_task_type(message, plan, {"memory_context": memory_context or {}}))
        plan["routing_source"] = str(plan.get("routing_source") or ("hybrid" if HybridRouter is not None else "llm"))
        log_orchestration("routing_decision", task_type=plan.get("task_type"), routing_source=plan.get("routing_source"), execution_mode=plan.get("execution_mode"), use_web=plan.get("use_web"))
        return plan

    async def governor(self, message: str, memory_context: dict | None = None) -> dict:
        memory_context = memory_context or {}
        personal_model = memory_context.get("personal_model") or {}
        try:
            return await self.router.analyze_governor(message, personal_model=personal_model)
        except Exception:
            return {"alignment_score": 100, "risk_pattern": "none", "intervention_level": 0, "recommended_action": "answer", "opening_line": "", "sharp_question": "", "notes": ""}

    def needs_approval(self, plan: dict, message: str) -> bool:
        plan = _normalize_plan(plan)
        if plan.get("suggest_memory_write") and not (message or "").strip().startswith("תזכור:"):
            return True
        return plan.get("suggested_automation_level", 0) > 1

    def format_approval_request(self, plan: dict) -> str:
        plan = _normalize_plan(plan)
        lines = [
            "צריך אישור לפני שאני ממשיך.",
            f"רמת האוטומציה המוצעת: Level {plan.get('suggested_automation_level', 0)}.",
        ]
        if plan.get("reason"):
            lines.append(f"למה: {plan['reason']}")
        gov = plan.get("governors") or {}
        gov_parts = []
        for k in ["max_turns", "max_execution_time_seconds"]:
            if gov.get(k) is not None:
                gov_parts.append(f"{k}={gov[k]}")
        if gov_parts:
            lines.append("מגבלות: " + ", ".join(gov_parts))
        if plan.get("suggest_memory_write") and isinstance(plan.get("memory_to_write"), dict):
            mem = plan["memory_to_write"]
            lines.extend([
                "",
                "אני מציע לשמור את זה לזיכרון:",
                f"type: {mem.get('type')}",
                f"key: {mem.get('key')}",
                f"value: {mem.get('value')}",
            ])
        lines.append("לאשר? (כן / לא / שנה רמה)")
        return "\n".join(lines)

    def build_execution_plan(self, message: str, plan: dict, context: dict | None = None) -> dict:
        plan = _normalize_plan(plan)
        resolved_task_type = self._resolve_task_type(message, plan, context or {})
        sequence = []
        if resolved_task_type and resolved_task_type in TASK_AGENT_MAP:
            sequence.append(TASK_AGENT_MAP[resolved_task_type])
        if plan.get("require_verification") or plan.get("require_code_review"):
            sequence.append("verification")
        return {
            "agent_sequence": sequence,
            "task_type": resolved_task_type,
            "routing_source": plan.get("routing_source") or "llm",
            "use_execution": True,
            "use_verification": bool(plan.get("require_verification") or plan.get("require_code_review")),
            "reason": plan.get("reason") or "default execution path",
        }

    def _resolve_task_type(self, message: str, plan: dict, context: dict | None = None) -> str | None:
        explicit = str(plan.get("task_type") or "").strip()
        if explicit == "personal_synthesis":
            return "personal_synthesis"
        if explicit in TASK_AGENT_MAP:
            return explicit
        msg = (message or "").lower()
        if any(k in msg for k in ["relationship", "dating", "social", "זוגיות", "אקסית", "קשר", "בחורה", "דייט", "רגשות", "תקשורת"]):
            return "relationships"
        if any(k in msg for k in ["business", "strategy", "offer", "pricing", "gtm", "growth", "עסק", "אסטרטגיה", "הצעה", "מוצר", "לקוחות", "מכירות", "מוניטיזציה"]):
            return "business_strategy"
        if any(k in msg for k in ["ai", "artificial intelligence", "machine learning", "llm", "gpt", "claude", "gemini", "anthropic", "openai", "מודל", "מודלים", "בינה מלאכותית", "למידת מכונה", "אייגנט", "אייגנטים"]):
            return "ai_expert"
        return None

    async def execute(self, message: str, plan: dict, context: dict | None = None, resume_state: dict | None = None) -> str | dict:
        plan = _normalize_plan(plan)
        context = context or {}
        start = time.time()
        if not plan.get("task_type"):
            plan["task_type"] = self._resolve_task_type(message, plan, context)
        plan.setdefault("routing_source", "llm")
        specialized_result = await self._try_run_specialized_agent(message, plan, context)
        if specialized_result is not None:
            return specialized_result
        if plan.get("execution_mode") == "agent_loop" and run_agent_loop is not None:
            return await run_agent_loop(message=message, plan=plan, context=context, resume_state=resume_state)
        result = await self._execute_direct(message, plan, context)
        print(f"Execution time: {time.time() - start:.2f}s")
        return result

    async def _try_run_specialized_agent(self, message: str, plan: dict, context: dict) -> str | dict | None:
        task_type = plan.get("task_type")
        agent_name = TASK_AGENT_MAP.get(task_type)
        if not agent_name:
            return None
        agent = self.agent_registry.get(agent_name)
        run_fn = getattr(agent, "run", None) if agent else None
        if not callable(run_fn):
            return None
        task_payload = {"type": task_type, "message": message, "plan": plan}
        agent_context = {"orchestrator_context": context, "memory_context": context.get("memory_context")}
        try:
            raw_routed = await run_fn(task_payload, agent_context)
            routed = normalize_agent_result(agent_name, raw_routed, fallback_note="specialized agent invalid result")
        except Exception as e:
            print(f"Specialized agent '{agent_name}' failed, fallback to default flow: {e}")
            return None
        if routed.get("status") == "not_implemented" or routed.get("should_fallback"):
            return None
        output = routed.get("output")
        if isinstance(output, str) and output.strip():
            # Never run Claude sanity_check on a web-grounded realtime answer —
            # Claude has no web access and will overwrite current news with
            # stale cutoff knowledge ("up to April 2024...").
            if (plan.get("require_verification") or plan.get("require_code_review")) and not plan.get("grounded_web"):
                verifier = self.agent_registry.get("verification")
                verify_fn = getattr(verifier, "run", None) if verifier else None
                if callable(verify_fn):
                    verified = await verify_fn({"type": "verification", "message": message, "draft_output": output, "plan": plan}, agent_context)
                    if isinstance(verified, dict) and isinstance(verified.get("output"), str):
                        return verified["output"]
            return output
        return None

    async def _execute_direct(self, message: str, plan: dict, context: dict) -> str:
        memory_context = context.get("memory_context")
        if context.get("cancelled"):
            return "נעצר."
        result, provider_used = await self.model_router.generate(message=message, plan=plan, memory_context=memory_context)
        # Same guard as the specialized path: never run a non-web verifier over
        # a web-grounded realtime answer.
        if plan.get("require_verification") and not plan.get("grounded_web"):
            checked = await sanity_check_answer(result, message, None)
            if checked and checked.strip():
                result = checked.strip()
        if plan.get("require_code_review") and not plan.get("grounded_web"):
            checked = await review_and_improve_code(result, message)
            if checked and checked.strip():
                result = checked.strip()
        print(f"Provider used: {provider_used}")
        return result
