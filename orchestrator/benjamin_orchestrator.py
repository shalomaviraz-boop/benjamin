"""Benjamin Orchestrator: Level-driven execution with approval gates and escalation.

Level 0-2 → direct path (Gemini + optional Claude, fast).
Level 3+  → Agent Loop (plan→execute→observe cycle).
"""
import asyncio
import time

from experts.gemini_client import FAST_MODEL, generate_fast, generate_web
from experts.claude_client import review_and_improve_code, sanity_check_answer
from experts.gpt_orchestrator import decide
from memory.memory_store import format_memory_for_worker
from orchestrator.agent_loop import run_agent_loop

LEVEL_FOR_WEB = 1
LEVEL_FOR_CLAUDE = 2
LEVEL_FOR_REFINEMENT = 3
MAX_REFINEMENT_PASSES = 1


class BenjaminOrchestrator:
    """GPT = Brain. Gemini = Worker. Claude = Quality layer. Level-driven."""

    def __init__(self):
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def plan(self, message: str, memory_context: dict | None = None) -> dict:
        """Get execution plan from GPT."""
        return await asyncio.to_thread(decide, message, memory_context)

    def needs_approval(self, plan: dict, message: str = "") -> bool:
        level = plan["suggested_automation_level"]
        suggest_mem = plan.get("suggest_memory_write", False)
        explicit_remember = message.strip().lower().startswith(("תזכור", "remember"))
        if suggest_mem and not explicit_remember:
            return True
        return level > 1

    def format_approval_request(self, plan: dict) -> str:
        level = plan["suggested_automation_level"]
        mode = plan.get("execution_mode", "direct")
        tools = plan.get("tools_required", [])
        gov = plan.get("governors", {})
        reason = plan.get("reason", "")
        suggest_mem = plan.get("suggest_memory_write", False)
        mem_to_write = plan.get("memory_to_write")

        mode_text = "Agent Loop" if mode == "agent_loop" else "ביצוע ישיר"
        tools_text = ", ".join(tools) if tools else "ללא כלים מיוחדים"

        lines = [
            f"נדרש {mode_text} עם גישת {tools_text}.",
            f"רמת אוטומציה מוצעת: Level {level}.",
        ]
        if suggest_mem and mem_to_write:
            lines.append(
                f"שמירת זיכרון מוצעת: {mem_to_write.get('key', '')} — "
                f"{str(mem_to_write.get('value', ''))[:50]}..."
            )
        elif suggest_mem:
            lines.append("שמירת מידע אישי מוצעת (לאחר אישור).")

        if gov:
            gov_parts = []
            if "max_budget_usd" in gov:
                gov_parts.append(f"budget=${gov['max_budget_usd']}")
            if "max_turns" in gov:
                gov_parts.append(f"turns={gov['max_turns']}")
            if "max_execution_time_seconds" in gov:
                gov_parts.append(f"time={gov['max_execution_time_seconds']} שניות")
            if gov_parts:
                lines.append(f"Governors: {', '.join(gov_parts)}.")

        if reason:
            lines.append(f"סיבה: {reason}")
        lines.append("לאשר? (כן / לא / שנה רמה)")

        return "\n".join(lines)

    async def execute(
        self,
        message: str,
        plan: dict,
        context: dict | None = None,
        resume_state: dict | None = None,
    ) -> str | dict:
        """Route to direct path (level 0-2) or agent loop (level 3+).

        Returns str for a final answer, or dict when mid-loop escalation
        needs user approval.
        """
        if context is None:
            context = {"cancelled": False}

        if plan["suggested_automation_level"] >= 3:
            return await self._execute_agent_loop(
                message, plan, context, resume_state,
            )

        return await self._execute_direct(message, plan, context)

    # ------------------------------------------------------------------
    # Level 3+ — Agent Loop
    # ------------------------------------------------------------------

    async def _execute_agent_loop(
        self,
        message: str,
        plan: dict,
        context: dict,
        resume_state: dict | None,
    ) -> str | dict:
        self._log_plan(plan)
        print("Delegating to Agent Loop...")

        loop_result = await run_agent_loop(message, plan, context, resume_state)

        if loop_result.get("needs_approval"):
            return loop_result

        steps = loop_result.get("steps", [])
        print(
            f"Agent Loop completed | steps={len(steps)} | "
            f"stopped={loop_result.get('stopped', False)}"
        )
        if loop_result.get("escalations"):
            print(f"Escalations: {loop_result['escalations']}")
        print(f"Tools used: {loop_result.get('tools_used', [])}")
        print("Success: True")

        return loop_result["final_answer"]

    # ------------------------------------------------------------------
    # Level 0-2 — Direct path (unchanged behaviour)
    # ------------------------------------------------------------------

    async def _execute_direct(
        self, message: str, plan: dict, context: dict,
    ) -> str:
        approved_level = plan["suggested_automation_level"]
        current_level = approved_level
        refinement_count = 0
        start_time = time.time()
        escalations: list[dict] = []

        task_state = {
            "user_input": message,
            "approved_level": approved_level,
            "effective_level": current_level,
            "web_used": False,
            "claude_called": False,
            "claude_applied": False,
            "refinement_triggered": False,
        }

        gov = plan.get("governors", {})
        max_time = gov.get("max_execution_time_seconds")
        max_turns = gov.get("max_turns")
        turns = 0

        def can_use(required_level: int) -> bool:
            nonlocal current_level
            if required_level <= current_level:
                return True
            if required_level <= approved_level + 1:
                esc = {
                    "current_level": current_level,
                    "requested_level": required_level,
                    "reason": f"Capability requires level {required_level}",
                }
                print(f"Escalation Proposal (auto-approved): {esc}")
                current_level = required_level
                task_state["effective_level"] = current_level
                escalations.append(esc)
                return True
            print(
                f"Escalation blocked: level {required_level} "
                f"> approved+1 ({approved_level}+1)"
            )
            return False

        def check_governors() -> bool:
            if max_time and (time.time() - start_time) > max_time:
                return False
            if max_turns and turns >= max_turns:
                return False
            return True

        self._log_plan(plan)

        mem_ctx = context.get("memory_context")
        worker_prompt = format_memory_for_worker(mem_ctx) + message

        try:
            # Step 1: Gemini execution
            use_web = plan["use_web"] and can_use(LEVEL_FOR_WEB)
            task_state["web_used"] = use_web
            print(f"Tools enabled: {use_web}")

            if use_web:
                result = await asyncio.to_thread(generate_web, worker_prompt)
            else:
                result = await asyncio.to_thread(generate_fast, worker_prompt)
            turns += 1

            if context.get("cancelled"):
                return "נעצר."

            if not check_governors():
                self._print_summary(
                    task_state, escalations, start_time, governor_limited=True,
                )
                return result

            # Step 2: Claude verification (level 2+)
            if plan["require_verification"] and can_use(LEVEL_FOR_CLAUDE):
                task_state["claude_called"] = True
                checked = await asyncio.to_thread(
                    sanity_check_answer, result, message, None,
                )
                turns += 1
                output_changed = checked and checked.strip() != result.strip()

                if output_changed:
                    task_state["claude_applied"] = True
                    if (
                        can_use(LEVEL_FOR_REFINEMENT)
                        and refinement_count < MAX_REFINEMENT_PASSES
                        and check_governors()
                    ):
                        print(
                            "Claude suggested corrections. "
                            "Running one refinement pass..."
                        )
                        refinement_prompt = (
                            worker_prompt + "\n\nClaude feedback:\n" + checked
                        )
                        if use_web:
                            result = await asyncio.to_thread(
                                generate_web, refinement_prompt,
                            )
                        else:
                            result = await asyncio.to_thread(
                                generate_fast, refinement_prompt,
                            )
                        turns += 1
                        refinement_count += 1
                        task_state["refinement_triggered"] = True
                        print(f"Refinement pass triggered: {refinement_count}")
                    else:
                        result = checked
                else:
                    print("No refinement needed.")

            if context.get("cancelled"):
                return "נעצר."

            if not check_governors():
                self._print_summary(
                    task_state, escalations, start_time, governor_limited=True,
                )
                return result

            # Step 3: Claude code review (level 2+)
            if plan["require_code_review"] and can_use(LEVEL_FOR_CLAUDE):
                task_state["claude_called"] = True
                improved = await asyncio.to_thread(
                    review_and_improve_code, result, message,
                )
                turns += 1
                output_changed = improved and improved.strip() != result.strip()

                if output_changed:
                    task_state["claude_applied"] = True
                    if (
                        can_use(LEVEL_FOR_REFINEMENT)
                        and refinement_count < MAX_REFINEMENT_PASSES
                        and check_governors()
                    ):
                        print(
                            "Claude suggested corrections. "
                            "Running one refinement pass..."
                        )
                        refinement_prompt = (
                            worker_prompt + "\n\nClaude feedback:\n" + improved
                        )
                        result = await asyncio.to_thread(
                            generate_fast, refinement_prompt,
                        )
                        turns += 1
                        refinement_count += 1
                        task_state["refinement_triggered"] = True
                        print(f"Refinement pass triggered: {refinement_count}")
                    else:
                        result = improved
                else:
                    print("No refinement needed.")

            self._print_summary(task_state, escalations, start_time)
            return result

        except Exception as e:
            print(f"Claude called: {task_state['claude_called']}")
            print(f"Claude applied: {task_state['claude_applied']}")
            print(f"Success: False | Error: {e}")
            raise

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _log_plan(plan: dict) -> None:
        gov = plan.get("governors", {})
        print(f"Routing decision: {plan}")
        print("Execution Plan:")
        print(f"  suggested_automation_level: {plan['suggested_automation_level']}")
        print(f"  execution_mode: {plan.get('execution_mode', 'direct')}")
        print(f"  tools_required: {plan.get('tools_required', [])}")
        print(f"  use_web: {plan['use_web']}")
        print(f"  require_verification: {plan['require_verification']}")
        print(f"  require_code_review: {plan['require_code_review']}")
        print(
            f"  require_task_decomposition: "
            f"{plan.get('require_task_decomposition', False)}"
        )
        print(f"  governors: {gov}")
        print(f"Model used: {FAST_MODEL}")
        print(f"Approval required: {plan['suggested_automation_level'] > 1}")

    @staticmethod
    def _print_summary(
        task_state: dict,
        escalations: list,
        start_time: float,
        governor_limited: bool = False,
    ) -> None:
        elapsed = round(time.time() - start_time, 2)
        print(f"Effective level: {task_state['effective_level']}")
        print(f"Claude called: {task_state['claude_called']}")
        print(f"Claude applied: {task_state['claude_applied']}")
        if task_state.get("refinement_triggered"):
            print("Refinement triggered: True")
        if escalations:
            print(f"Escalations: {escalations}")
        print(f"Execution time: {elapsed}s")
        if governor_limited:
            print("Success: True (governor-limited)")
        else:
            print("Success: True")
