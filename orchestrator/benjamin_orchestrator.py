"""
Benjamin Orchestrator
LLM Router (GPT) decides an execution plan → Gemini executes → Claude optionally verifies/reviews
Supports:
- Autonomy levels 0-5 (approval gate in handler)
- Direct execution (levels 0-2)
- Agent loop (levels 3+), with optional mid-run approval via returned dict
- Memory context injection to worker calls
- Memory write suggestion gating (requires approval unless explicit "תזכור:")
"""

from __future__ import annotations

import time
from typing import Any

from agents.agent_context import AgentContextState
from agents.registry import registry as agent_registry
from experts.gemini_client import FAST_MODEL, generate_fast, generate_web
from experts.gpt_orchestrator import GPTOrchestrator  # decide(message, memory_context) -> dict
from experts.claude_client import sanity_check_answer, review_and_improve_code
from utils.benjamin_identity import build_benjamin_user_prompt
from utils.logger import log_orchestration

try:
    from orchestrator.hybrid_router import HybridRouter
except Exception:  # pragma: no cover
    HybridRouter = None

from agents.agent_contract import normalize_agent_result
from orchestrator.validation_layer import ValidationLayer

# Agent loop (optional; exists in your project per your summary)
try:
    from orchestrator.agent_loop import run_agent_loop
except Exception:  # pragma: no cover
    run_agent_loop = None


MAX_REFINEMENT_PASSES = 1
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
}


def _shorten(s: str | None, n: int = 120) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n].rstrip() + "…"


def _bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    return default


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _normalize_plan(plan: dict) -> dict:
    """
    Hard-set defaults so orchestrator never crashes if router omitted keys.
    """
    plan = plan or {}
    plan.setdefault("suggested_automation_level", 0)
    plan.setdefault("execution_mode", "direct")
    plan.setdefault("tools_required", [])
    plan.setdefault("use_web", False)
    plan.setdefault("require_verification", False)
    plan.setdefault("require_code_review", False)
    plan.setdefault("require_task_decomposition", False)
    plan.setdefault("governors", {})
    plan.setdefault("reason", "")

    # Memory suggestion fields (may exist in your router prompt)
    plan.setdefault("suggest_memory_write", False)
    plan.setdefault("memory_to_write", None)

    # Normalize types
    plan["suggested_automation_level"] = max(0, min(5, _int(plan["suggested_automation_level"], 0)))
    plan["use_web"] = _bool(plan["use_web"], False)
    plan["require_verification"] = _bool(plan["require_verification"], False)
    plan["require_code_review"] = _bool(plan["require_code_review"], False)
    plan["require_task_decomposition"] = _bool(plan["require_task_decomposition"], False)
    plan["suggest_memory_write"] = _bool(plan["suggest_memory_write"], False)

    # execution_mode derived (keep if already explicit)
    if plan["execution_mode"] not in {"direct", "agent_loop"}:
        plan["execution_mode"] = "agent_loop" if plan["suggested_automation_level"] >= 3 else "direct"

    if not isinstance(plan["tools_required"], list):
        plan["tools_required"] = []

    if not isinstance(plan["governors"], dict):
        plan["governors"] = {}

    # Governors defaults (only if already used אצלך)
    # לא מכניס פה שום חובה חדשה — רק מוודא מבנה.
    return plan


class BenjaminOrchestrator:
    def __init__(self):
        self.gpt_router = GPTOrchestrator()
        self.router = HybridRouter(self.gpt_router) if HybridRouter is not None else self.gpt_router
        self.agent_registry = agent_registry
        self.validation_layer = ValidationLayer()

    async def plan(self, message: str, memory_context: dict | None = None) -> dict:
        plan = await self.router.decide(message, memory_context=memory_context)
        plan = _normalize_plan(plan)
        plan.setdefault("task_type", self._resolve_task_type(message, plan, {"memory_context": memory_context or {}}))
        plan.setdefault("routing_source", "hybrid" if HybridRouter is not None else "llm")
        print(f"Routing decision: {plan}")
        log_orchestration("routing_decision", task_type=plan.get("task_type"), routing_source=plan.get("routing_source"), execution_mode=plan.get("execution_mode"), use_web=plan.get("use_web"))
        return plan

    async def governor(self, message: str, memory_context: dict | None = None) -> dict:
        """
        Run Personal Governor analysis (internal, before execution).
        """
        memory_context = memory_context or {}
        personal_model = memory_context.get("user_profile") or {}
        g = await self.router.analyze_governor(message, personal_model=personal_model)
        print(f"Governor decision: {g}")
        return g

    def needs_approval(self, plan: dict, message: str) -> bool:
        """
        Approval rule:
        - If GPT suggests memory write and user didn't explicitly say 'תזכור:' → approval required.
        - Else: standard autonomy approval (Level > 1).
        """
        plan = _normalize_plan(plan)

        # Memory gate
        if plan.get("suggest_memory_write"):
            msg = (message or "").strip()
            if not msg.startswith("תזכור:"):
                return True

        level = plan.get("suggested_automation_level", 0)
        return level > 1

    def format_approval_request(self, plan: dict) -> str:
        plan = _normalize_plan(plan)

        level = plan.get("suggested_automation_level", 0)
        reason = plan.get("reason", "").strip()
        tools = plan.get("tools_required", [])

        lines = []
        lines.append("נדרש אישור לפני ביצוע.")
        lines.append(f"רמת אוטומציה מוצעת: Level {level}.")
        if reason:
            lines.append(f"סיבה: {reason}")
        if tools:
            lines.append(f"כלים נדרשים: {', '.join(tools)}")

        # Governors preview (אם קיים אצלך)
        gov = plan.get("governors") or {}
        if isinstance(gov, dict) and gov:
            # מציג רק מה שקיים בלי רעש
            gov_parts = []
            for k in ["max_budget_usd", "max_tokens", "max_turns", "max_execution_time_seconds"]:
                if k in gov and gov[k] is not None:
                    gov_parts.append(f"{k}={gov[k]}")
            if gov_parts:
                lines.append("מגבלות: " + ", ".join(gov_parts))

        # Memory preview
        if plan.get("suggest_memory_write") and isinstance(plan.get("memory_to_write"), dict):
            mem = plan["memory_to_write"]
            mtype = (mem.get("type") or "fact").strip()
            key = (mem.get("key") or "").strip()
            value = _shorten(str(mem.get("value") or ""), 120)

            lines.append("")
            lines.append("המערכת מציעה לשמור זיכרון:")
            lines.append(f"type: {mtype}")
            lines.append(f"key: {key}")
            lines.append(f"value: {value}")

        lines.append("לאשר? (כן / לא / שנה רמה)")
        return "\n".join(lines)

    def build_execution_plan(self, message: str, plan: dict, context: dict | None = None) -> dict:
        """
        Deterministic internal routing plan for multi-agent execution.
        Keeps behavior understandable and stable.
        """
        context = context or {}
        normalized = (message or "").strip().lower()

        # Signals
        is_memory_update = normalized.startswith("תזכור") or normalized.startswith("remember")
        is_news_like = any(
            k in normalized
            for k in [
                "news",
                "breaking",
                "market",
                "markets",
                "ai news",
                "עדכ",
                "חדשות",
                "אירוע",
                "שוק",
                "מאקרו",
            ]
        ) or bool(plan.get("use_web"))
        is_personal_context = any(
            k in normalized
            for k in [
                "about me",
                "what do you remember",
                "זוכר עליי",
                "זוכרת עליי",
                "אישי",
                "בשבילי",
            ]
        )
        is_complex = bool(plan.get("require_task_decomposition")) or any(
            k in normalized
            for k in [
                "architecture",
                "refactor",
                "design",
                "plan",
                "project",
                "מימוש",
                "תכנן",
                "תוכנית",
                "ארכיטקטורה",
                "ריפקטור",
            ]
        )
        is_quick_casual = (
            len(normalized) < 70
            and not is_memory_update
            and not is_news_like
            and not is_complex
            and not bool(plan.get("require_verification") or plan.get("require_code_review"))
        )
        needs_verification = bool(plan.get("require_verification") or plan.get("require_code_review"))

        use_memory = False
        use_planning = False
        use_research = False
        use_execution = True
        use_verification = False
        reason = "default execution path"

        if is_memory_update:
            use_memory = True
            use_execution = True
            use_verification = False
            reason = "memory update request"
        elif is_news_like:
            use_memory = True
            use_research = True
            use_execution = True
            use_verification = needs_verification
            reason = "factual/current-events/news-like request"
        elif is_complex:
            use_memory = True
            use_planning = True
            use_execution = True
            use_verification = True if needs_verification or plan.get("execution_mode") == "agent_loop" else False
            reason = "complex planning/project request"
        elif is_personal_context:
            use_memory = True
            use_execution = True
            use_verification = needs_verification
            reason = "personal/contextual guidance request"
        elif is_quick_casual:
            use_memory = False
            use_execution = True
            use_verification = False
            reason = "quick casual request"
        else:
            use_memory = bool(context.get("memory_context"))
            use_execution = True
            use_verification = needs_verification
            reason = "general request with safe defaults"

        resolved_task_type = self._resolve_task_type(message, plan, context)
        routing_source = str(plan.get("routing_source") or "llm").strip().lower()

        sequence: list[str] = []
        if use_memory:
            sequence.append("memory")
        if use_planning:
            sequence.append("planning")
        if use_research:
            sequence.append("research")
        if use_execution:
            sequence.append("execution")
        if use_verification:
            sequence.append("verification")

        prioritized_agent = TASK_AGENT_MAP.get(resolved_task_type) if resolved_task_type else None
        if prioritized_agent and prioritized_agent not in sequence:
            sequence.insert(0, prioritized_agent)

        execution_plan = {
            "use_memory": use_memory,
            "use_planning": use_planning,
            "use_research": use_research,
            "use_execution": use_execution,
            "use_verification": use_verification,
            "agent_sequence": sequence,
            "reason": reason,
            "task_type": resolved_task_type,
            "routing_source": routing_source,
        }
        print(f"Agent routing plan: {execution_plan}")
        log_orchestration("execution_plan", task_type=resolved_task_type, routing_source=routing_source, agents=sequence, reason=reason)
        return execution_plan

    async def run_agent_sequence(
        self,
        message: str,
        plan: dict,
        context: dict | None,
        execution_plan: dict,
    ) -> str | None:
        """
        Run the selected agent sequence once (no autonomous loops).
        Returns final text if successfully produced by agents, else None for fallback.
        """
        context = context or {}
        sequence = execution_plan.get("agent_sequence") or []
        if not isinstance(sequence, list) or not sequence:
            return None

        actual_ran: list[str] = []
        shared = AgentContextState(
            task=plan,
            user_message=message,
            memory_context=context.get("memory_context") if isinstance(context.get("memory_context"), dict) else {},
            metadata={"routing_plan": execution_plan, "chosen_sequence": sequence, "agent_capabilities": {}},
        )

        for agent_name in sequence:
            agent = self.agent_registry.get(agent_name)
            shared.metadata.setdefault("agent_capabilities", {})[agent_name] = self.agent_registry.get_capabilities(agent_name) if hasattr(self.agent_registry, "get_capabilities") else {}
            if agent is None:
                shared.add_log("orchestrator", f"{agent_name}: missing agent, skipped")
                continue

            run_fn = getattr(agent, "run", None)
            if not callable(run_fn):
                shared.add_log("orchestrator", f"{agent_name}: run() unavailable, skipped")
                continue

            task_payload = {
                "type": agent_name,
                "message": shared.user_message,
                "original_message": message,
                "plan": plan,
                "draft_output": shared.execution_output.get("output") if isinstance(shared.execution_output, dict) else "",
                "planning": shared.planning_output,
                "agent_context": shared.to_dict(),
            }
            agent_context = {
                "orchestrator_context": context,
                "memory_context": shared.memory_context,
                "agent_context": shared.to_dict(),
            }

            try:
                raw_result = await run_fn(task_payload, agent_context)
                result = normalize_agent_result(agent_name, raw_result, fallback_note=f"{agent_name}: invalid result")
                actual_ran.append(agent_name)
            except NotImplementedError:
                shared.add_log("orchestrator", f"{agent_name}: not implemented, skipped")
                continue
            except Exception as e:
                shared.add_log("orchestrator", f"{agent_name}: error ({e}), skipped")
                continue

            if isinstance(result.get("agent_context"), dict):
                shared = AgentContextState.from_dict(result.get("agent_context"))
            if agent_name == "planning":
                shared.planning_output = result
            elif agent_name == "execution":
                out = result.get("output")
                if isinstance(out, str):
                    shared.execution_output = result
                    shared.final_output = out
            elif agent_name == "verification":
                shared.verification_output = result
                if isinstance(result.get("output"), str) and result.get("approved") is True:
                    shared.final_output = result["output"]

        print(f"Agents ran: {actual_ran}")
        if shared.logs:
            print(f"Agent context logs: {shared.logs}")
        print(f"Agent context metadata: {shared.metadata}")

        verification_output = shared.verification_output
        if isinstance(verification_output, dict):
            if verification_output.get("approved") is True:
                out = verification_output.get("output")
                if isinstance(out, str):
                    return out
            notes = verification_output.get("notes")
            if isinstance(notes, str) and notes.strip():
                return notes
            return None

        execution_out = shared.execution_output.get("output") if isinstance(shared.execution_output, dict) else ""
        if isinstance(execution_out, str) and execution_out.strip():
            return execution_out

        planning_output = shared.planning_output
        if isinstance(planning_output, dict):
            objective = str(planning_output.get("objective") or "").strip()
            steps = planning_output.get("steps") or []
            if objective and isinstance(steps, list):
                bullet_steps = "\n".join(f"- {str(s).strip()}" for s in steps if str(s).strip())
                if bullet_steps:
                    return f"מטרה: {objective}\n\nתוכנית:\n{bullet_steps}"
        return None

    async def execute(
        self,
        message: str,
        plan: dict,
        context: dict | None = None,
        resume_state: dict | None = None,
    ) -> str | dict:
        """
        Returns:
        - str: final answer
        - dict: when agent loop needs mid-execution approval (handler will store resume_state)
        """
        plan = _normalize_plan(plan)
        context = context or {}
        context.setdefault("task_type", plan.get("task_type"))
        context.setdefault("routing_source", plan.get("routing_source"))
        start = time.time()

        if not plan.get("task_type"):
            plan["task_type"] = self._resolve_task_type(message, plan, context)
        plan.setdefault("routing_source", "llm")

        self._log_plan(plan)

        specialized_result = await self._try_run_specialized_agent(message, plan, context)
        if specialized_result is not None:
            validation = self.validation_layer.validate(message=message, plan=plan, result=specialized_result)
            log_orchestration("specialized_result", task_type=plan.get("task_type"), routing_source=plan.get("routing_source"), valid=validation["is_valid"], summary=validation["summary"])
            if validation["is_valid"]:
                elapsed = time.time() - start
                print(f"Execution time: {elapsed:.2f}s")
                return specialized_result

        execution_plan = self.build_execution_plan(message, plan, context)
        routed_result = await self.run_agent_sequence(message, plan, context, execution_plan)
        if routed_result is not None:
            validation = self.validation_layer.validate(message=message, plan=plan, execution_plan=execution_plan, result=routed_result)
            log_orchestration("agent_sequence_result", task_type=plan.get("task_type"), routing_source=plan.get("routing_source"), agents=execution_plan.get("agent_sequence"), valid=validation["is_valid"], summary=validation["summary"])
            if validation["is_valid"]:
                elapsed = time.time() - start
                print(f"Execution time: {elapsed:.2f}s")
                return routed_result

        if plan.get("execution_mode") == "agent_loop":
            result = await self._execute_agent_loop(message, plan, context, resume_state)
        else:
            result = await self._execute_direct(message, plan, context)

        validation = self.validation_layer.validate(message=message, plan=plan, execution_plan=execution_plan, result=result)
        log_orchestration("fallback_result", task_type=plan.get("task_type"), routing_source=plan.get("routing_source"), valid=validation["is_valid"], summary=validation["summary"])
        elapsed = time.time() - start
        print(f"Execution time: {elapsed:.2f}s")
        return result if validation["is_valid"] else "מצטער, לא הצלחתי להשלים את הבקשה כרגע. נסה לנסח מחדש בקצרה."

    def _resolve_task_type(self, message: str, plan: dict, context: dict) -> str | None:
        explicit = (context.get("task_type") or plan.get("task_type") or "").strip().lower()
        if explicit in TASK_AGENT_MAP:
            return explicit

        tools_required = [str(t).lower() for t in (plan.get("tools_required") or [])]
        if any("memory" in t for t in tools_required) or plan.get("suggest_memory_write"):
            return "memory"
        if any(t in tools_required for t in ["files", "code", "repo"]):
            return "code"
        if any(t in tools_required for t in ["calendar", "assistant"]):
            return "assistant"
        if any(t in tools_required for t in ["finance", "market_data"]):
            return "finance"
        if any(t in tools_required for t in ["fitness", "nutrition", "health"]):
            return "fitness_health"
        if plan.get("require_task_decomposition"):
            return "planning"
        if plan.get("require_code_review"):
            return "code"
        if plan.get("use_web") and any(k in (message or "").lower() for k in ["מניה", "מניות", "מדד", "שוק", "מאקרו", "finance", "stock", "stocks", "macro", "ta35", "spx", "qqq", "spy"]):
            return "finance"
        if plan.get("execution_mode") == "agent_loop":
            return "execution"

        msg = (message or "").lower()
        if any(k in msg for k in ["אימון", "כושר", "תזונה", "מסה", "חיטוב", "קלור", "חלבון", "ארוחה", "diet", "nutrition", "workout", "bulk", "cut"]):
            return "fitness_health"
        if any(k in msg for k in ["קוד", "python", "bug", "error", "exception", "stack trace", "refactor", "architecture"]):
            return "code"
        if any(k in msg for k in ["מניה", "מניות", "מדד", "שוק", "מאקרו", "finance", "stock", "stocks", "macro", "ta35", "spx", "qqq", "spy"]):
            return "finance"
        if any(k in msg for k in ["תזכיר", "יומן", "לו""ז", "משימה", "תארגן", "calendar", "schedule", "reminder", "assistant"]):
            return "assistant"
        if any(k in msg for k in ["research", "חקור", "בדוק מקורות", "market scan", "news scan", "חדשות", "news"]):
            return "research"
        if any(k in msg for k in ["memory", "תזכור", "זכור"]):
            return "memory"
        if any(k in msg for k in ["plan", "תכנן", "תוכנית"]):
            return "planning"
        if any(k in msg for k in ["verify", "אמת", "בדיקת אמינות"]):
            return "verification"
        if any(k in msg for k in ["execute", "הרץ", "בצע"]):
            return "execution"
        if any(k in msg for k in ["relationship", "dating", "social", "זוגיות", "אקסית", "קשר", "בחורה", "דייט", "רגשות", "תקשורת"]):
            return "relationships"
        if any(k in msg for k in ["business", "strategy", "offer", "pricing", "gtm", "growth", "עסק", "אסטרטגיה", "הצעה", "מוצר", "לקוחות", "מכירות", "מוניטיזציה"]):
            return "business_strategy"
        if any(k in msg for k in ["ai", "artificial intelligence", "machine learning", "llm", "gpt", "claude", "gemini", "anthropic", "openai", "מודל", "מודלים", "בינה מלאכותית", "למידת מכונה", "אייגנט", "אייגנטים"]):
            return "ai_expert"

        return None

    async def _try_run_specialized_agent(self, message: str, plan: dict, context: dict) -> str | dict | None:
        task_type = self._resolve_task_type(message, plan, context)
        if not task_type:
            return None

        agent_name = TASK_AGENT_MAP.get(task_type)
        agent = self.agent_registry.get(agent_name) if agent_name else None
        if agent is None:
            return None

        run_fn = getattr(agent, "run", None)
        if not callable(run_fn):
            return None

        task_payload = {
            "type": task_type,
            "message": message,
            "plan": plan,
        }
        agent_context = {
            "orchestrator_context": context,
            "memory_context": context.get("memory_context"),
        }

        try:
            raw_routed = await run_fn(task_payload, agent_context)
            routed = normalize_agent_result(agent_name, raw_routed, fallback_note="specialized agent invalid result")
        except NotImplementedError:
            return None
        except Exception as e:
            print(f"Specialized agent '{agent_name}' failed, fallback to default flow: {e}")
            return None

        if routed.get("status") == "not_implemented" or routed.get("should_fallback"):
            return None
        if task_type == "execution":
            output = routed.get("output")
            if not isinstance(output, str):
                return None

            need_verify = bool(plan.get("require_verification") or plan.get("require_code_review"))
            if not need_verify:
                return output

            verifier = self.agent_registry.get("verification")
            verify_fn = getattr(verifier, "run", None) if verifier else None
            if not callable(verify_fn):
                return output

            verify_task = {
                "type": "verification",
                "message": message,
                "original_message": message,
                "draft_output": output,
                "plan": plan,
            }
            try:
                verified = await verify_fn(verify_task, agent_context)
            except Exception as e:
                print(f"Verification agent failed, returning execution output: {e}")
                return output

            if not isinstance(verified, dict):
                return output
            if verified.get("approved") is True:
                verified_output = verified.get("output")
                return verified_output if isinstance(verified_output, str) else output
            notes = verified.get("notes")
            if isinstance(notes, str) and notes.strip():
                return notes
            return "הפלט לא עבר אימות."
        if task_type == "verification":
            if routed.get("approved") is True and isinstance(routed.get("output"), str):
                return routed["output"]
            notes = routed.get("notes")
            if isinstance(notes, str) and notes.strip():
                return notes
            return None
        if isinstance(routed.get("final_answer"), str):
            return routed["final_answer"]
        if isinstance(routed.get("result"), str):
            return routed["result"]
        if isinstance(routed.get("output"), str):
            return routed["output"]
        if task_type == "planning":
            objective = str(routed.get("objective") or "").strip()
            steps = routed.get("steps") or []
            if objective and isinstance(steps, list):
                bullet_steps = "\n".join(f"- {str(s).strip()}" for s in steps if str(s).strip())
                if bullet_steps:
                    return f"מטרה: {objective}\n\nתוכנית:\n{bullet_steps}"
        return None

    def _log_plan(self, plan: dict) -> None:
        print("Execution Plan:")
        print(f"  suggested_automation_level: {plan.get('suggested_automation_level')}")
        print(f"  execution_mode: {plan.get('execution_mode')}")
        print(f"  tools_required: {plan.get('tools_required')}")
        print(f"  use_web: {plan.get('use_web')}")
        print(f"  require_verification: {plan.get('require_verification')}")
        print(f"  require_code_review: {plan.get('require_code_review')}")
        print(f"  require_task_decomposition: {plan.get('require_task_decomposition')}")
        print(f"  governors: {plan.get('governors')}")
        print(f"  task_type: {plan.get('task_type')}")
        print(f"  routing_source: {plan.get('routing_source')}")
        if plan.get("suggest_memory_write"):
            mem = plan.get("memory_to_write")
            print(f"  suggest_memory_write: True | memory_to_write: {mem}")

    async def _execute_direct(self, message: str, plan: dict, context: dict) -> str:
        """
        Direct execution (levels 0-2):
        - Gemini fast or web
        - optional Claude verification
        - optional Claude code review
        - optional single refinement pass (if Claude changes output)
        """
        memory_context = context.get("memory_context")

        model_used = FAST_MODEL
        use_web = bool(plan.get("use_web"))
        print(f"Model used: {model_used}")
        print(f"Tools enabled: {use_web}")

        # Step 1: Gemini
        if context.get("cancelled"):
            return "נעצר."

        benjamin_prompt = build_benjamin_user_prompt(message)
        if use_web:
            result = await generate_web(benjamin_prompt, memory_context=memory_context)
        else:
            result = await generate_fast(benjamin_prompt, memory_context=memory_context)

        claude_called = False
        claude_applied = False
        refinement_triggered = False
        refinement_count = 0

        # Step 2: Claude verification
        if context.get("cancelled"):
            return "נעצר."

        if plan.get("require_verification"):
            claude_called = True
            claude_out = await sanity_check_answer(result)
            if claude_out and claude_out.strip() != result.strip():
                claude_applied = True
                if refinement_count < MAX_REFINEMENT_PASSES:
                    print("Claude suggested corrections. Running one refinement pass...")
                    refinement_triggered = True
                    refinement_count += 1
                    # Re-run Gemini with appended feedback
                    revised_prompt = (
                        f"{build_benjamin_user_prompt(message)}\n\n"
                        f"---\n"
                        f"Claude feedback (apply fixes, keep final answer concise):\n{claude_out}\n"
                        f"---\n"
                        f"Return the corrected final answer only."
                    )
                    if use_web:
                        result = await generate_web(revised_prompt, memory_context=memory_context)
                    else:
                        result = await generate_fast(revised_prompt, memory_context=memory_context)
                else:
                    result = claude_out

        # Step 3: Claude code review
        if context.get("cancelled"):
            return "נעצר."

        if plan.get("require_code_review"):
            claude_called = True
            claude_out = await review_and_improve_code(result)
            if claude_out and claude_out.strip() != result.strip():
                claude_applied = True
                if refinement_count < MAX_REFINEMENT_PASSES:
                    print("Claude suggested corrections. Running one refinement pass...")
                    refinement_triggered = True
                    refinement_count += 1
                    revised_prompt = (
                        f"{build_benjamin_user_prompt(message)}\n\n"
                        f"---\n"
                        f"Claude code review feedback (apply fixes):\n{claude_out}\n"
                        f"---\n"
                        f"Return the corrected final code/answer only."
                    )
                    # Code usually doesn't need web
                    result = await generate_fast(revised_prompt, memory_context=memory_context)
                else:
                    result = claude_out

        print(f"Effective level: {plan.get('suggested_automation_level')}")
        print(f"Claude called: {claude_called}")
        print(f"Claude applied: {claude_applied}")
        if refinement_triggered:
            print("Refinement triggered: True")

        print("Success: True")
        return result

    async def _execute_agent_loop(
        self,
        message: str,
        plan: dict,
        context: dict,
        resume_state: dict | None,
    ) -> str | dict:
        """
        Agent loop (levels 3+).
        run_agent_loop may return:
        - str final answer
        - dict needs_approval w/ resume_state and proposed_plan
        """
        if run_agent_loop is None:
            return await self._execute_direct(message, plan, context)

        return await run_agent_loop(
            message=message,
            plan=plan,
            context=context,
            resume_state=resume_state,
        )