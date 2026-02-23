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

from experts.gemini_client import FAST_MODEL, generate_fast, generate_web
from experts.gpt_orchestrator import GPTOrchestrator  # decide(message, memory_context) -> dict
from experts.claude_client import sanity_check_answer, review_and_improve_code

# Agent loop (optional; exists in your project per your summary)
try:
    from orchestrator.agent_loop import run_agent_loop
except Exception:  # pragma: no cover
    run_agent_loop = None


MAX_REFINEMENT_PASSES = 1


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
       self.router = GPTOrchestrator()

    async def plan(self, message: str, memory_context: dict | None = None) -> dict:
        plan = await self.router.decide(message, memory_context=memory_context)
        plan = _normalize_plan(plan)
        print(f"Routing decision: {plan}")
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
        start = time.time()

        self._log_plan(plan)

        # Execution path
        if plan["execution_mode"] == "agent_loop":
            if run_agent_loop is None:
                # Fallback: execute direct if agent loop engine not available
                result = await self._execute_direct(message, plan, context)
            else:
                result = await self._execute_agent_loop(message, plan, context, resume_state)
        else:
            result = await self._execute_direct(message, plan, context)

        elapsed = time.time() - start
        print(f"Execution time: {elapsed:.2f}s")
        return result

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

        if use_web:
            result = await generate_web(message, memory_context=memory_context)
        else:
            result = await generate_fast(message, memory_context=memory_context)

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
                        f"{message}\n\n"
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
                        f"{message}\n\n"
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