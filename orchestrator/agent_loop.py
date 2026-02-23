"""Agent Loop engine for Level 3+ autonomous execution.

Cycle: Plan → Execute → Observe → Update.
Each iteration the Planner generates 1-3 steps, the Executor runs them,
and results feed back into the next planning round.
"""
import asyncio
import json
import time

from experts.gemini_client import generate_fast, generate_web
from experts.claude_client import review_and_improve_code, sanity_check_answer
from memory.memory_store import format_memory_for_worker

LEVEL_FOR_WEB = 1
LEVEL_FOR_CLAUDE = 2
LEVEL_FOR_BASH = 3

DEFAULT_MAX_TURNS = 5
DEFAULT_MAX_TIME = 120

INTENT_MIN_LEVEL = {
    "research": 0,
    "summarize": 0,
    "finalize": 0,
    "write": 2,
    "edit": 2,
    "todo": 2,
    "verify": LEVEL_FOR_CLAUDE,
    "code_review": LEVEL_FOR_CLAUDE,
    "bash": LEVEL_FOR_BASH,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_available_intents(level: int) -> list[str]:
    return [i for i, min_lvl in INTENT_MIN_LEVEL.items() if min_lvl <= level]


def _is_bash_allowed(cmd: str) -> bool:
    parts = cmd.strip().split()
    if not parts:
        return False
    base = parts[0]
    if base == "ls":
        return True
    if base == "cat":
        return True
    if base == "git" and len(parts) >= 2 and parts[1] in ("status", "diff", "log"):
        return True
    if base == "python" and len(parts) >= 3 and parts[1] == "-m" and parts[2] == "pytest":
        return True
    return False


async def _run_safe_bash(cmd: str) -> str:
    cmd = cmd.strip()
    if not _is_bash_allowed(cmd):
        return f"[Blocked: '{cmd}' not in allowlist]"
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        out = (stdout.decode() if stdout else "")
        if stderr:
            out += "\n" + stderr.decode()
        return out.strip() or "[No output]"
    except asyncio.TimeoutError:
        return "[Bash timeout: 30s]"
    except Exception as e:
        return f"[Bash error: {e}]"


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

async def _plan_next_steps(
    message: str,
    completed_steps: list[dict],
    available_intents: list[str],
    next_step_id: int,
    use_web: bool,
) -> list[dict]:
    """Ask Gemini FAST to generate the next 1-3 steps as JSON."""
    if completed_steps:
        progress_lines = []
        for s in completed_steps:
            summary = s.get("result_summary", "")[:100]
            progress_lines.append(
                f"  Step {s['step_id']}: [{s['intent']}] {s['status']} — {summary}"
            )
        progress = "Completed steps:\n" + "\n".join(progress_lines)
    else:
        progress = "No steps completed yet."

    tools_note = "generate_fast"
    if use_web:
        tools_note += ", generate_web"

    prompt = (
        "You are a step planner. Given a task and progress, plan 1-3 next steps.\n\n"
        "CRITICAL: Return ONLY valid JSON. No markdown, no explanation.\n"
        f'{{"steps": [{{"step_id": {next_step_id}, "intent": "...", '
        f'"instruction": "...", "tools": ["..."]}}]}}\n\n'
        f"Valid intents: {', '.join(available_intents)}\n"
        f"Available execution tools: {tools_note}\n\n"
        f"Task: {message}\n\n"
        f"{progress}\n\n"
        f'Use "finalize" when the task is complete or enough info is gathered.\n'
        f"Start step_id from {next_step_id}."
    )

    raw = await asyncio.to_thread(generate_fast, prompt)

    try:
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        data = json.loads(text)
        steps = data.get("steps", [])
        for s in steps:
            s.setdefault("status", "pending")
            s.setdefault("result_summary", "")
            s.setdefault("tools", [])
        return steps[:3]
    except (json.JSONDecodeError, KeyError, IndexError):
        return [
            {
                "step_id": next_step_id,
                "intent": "finalize",
                "instruction": "Compile final answer from gathered information",
                "tools": ["generate_fast"],
                "status": "pending",
                "result_summary": "",
            }
        ]


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

def _worker_prompt(text: str, memory_context: dict | None) -> str:
    """Prepend memory context to worker prompt."""
    prefix = format_memory_for_worker(memory_context)
    return prefix + text if prefix else text


async def _execute_step(
    step: dict,
    message: str,
    plan: dict,
    current_level: int,
    prior_results: list[str],
    memory_context: dict | None = None,
) -> str:
    """Execute a single step and return its text result."""
    intent = step["intent"]
    instruction = step["instruction"]
    use_web = plan.get("use_web", False) and current_level >= LEVEL_FOR_WEB

    if intent == "research":
        prompt = _worker_prompt(instruction, memory_context)
        if use_web:
            return await asyncio.to_thread(generate_web, prompt)
        return await asyncio.to_thread(generate_fast, prompt)

    if intent == "verify":
        draft = prior_results[-1] if prior_results else instruction
        return await asyncio.to_thread(sanity_check_answer, draft, message, None)

    if intent == "code_review":
        draft = prior_results[-1] if prior_results else instruction
        return await asyncio.to_thread(review_and_improve_code, draft, message)

    if intent == "bash":
        return await _run_safe_bash(instruction)

    if intent in ("summarize", "finalize"):
        ctx = (
            "\n---\n".join(r for r in prior_results if r)
            if prior_results
            else instruction
        )
        prompt = (
            f"User request: {message}\n\n"
            f"Gathered information:\n{ctx}\n\n"
            "Provide a comprehensive final answer in the same language "
            "as the user's request."
        )
        prompt = _worker_prompt(prompt, memory_context)
        return await asyncio.to_thread(generate_fast, prompt)

    if intent in ("write", "edit", "todo"):
        return f"[Task noted: {instruction}]"

    return f"[Unknown intent: {intent}]"


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def run_agent_loop(
    message: str,
    plan: dict,
    context: dict,
    resume_state: dict | None = None,
) -> dict:
    """Run Plan→Execute→Observe loop. Returns structured result dict.

    Return keys:
      final_answer, steps, tools_used, escalations, stopped
      (+ needs_approval, approval_request_text, proposed_plan, resume_state
       when mid-loop escalation requires user approval)
    """
    approved_level = plan["suggested_automation_level"]
    current_level = approved_level
    use_web = plan.get("use_web", False)

    gov = plan.get("governors", {})
    max_turns = gov.get("max_turns", DEFAULT_MAX_TURNS)
    max_time = gov.get("max_execution_time_seconds", DEFAULT_MAX_TIME)

    if resume_state:
        completed_steps: list[dict] = resume_state["completed_steps"]
        results: list[str] = resume_state["results"]
        tools_used: list[str] = resume_state["tools_used"]
        escalations: list[dict] = resume_state["escalations"]
        iteration: int = resume_state["iteration"]
        next_step_id: int = resume_state["next_step_id"]
        elapsed_before: float = resume_state.get("elapsed_seconds", 0)
    else:
        completed_steps = []
        results = []
        tools_used = []
        escalations = []
        iteration = 0
        next_step_id = 1
        elapsed_before = 0.0

    start_time = time.time()
    memory_context = context.get("memory_context")

    def total_elapsed() -> float:
        return elapsed_before + (time.time() - start_time)

    def make_result(final_answer: str, stopped: bool = False, **extra) -> dict:
        r: dict = {
            "final_answer": final_answer,
            "steps": completed_steps,
            "tools_used": tools_used,
            "escalations": escalations,
            "stopped": stopped,
        }
        r.update(extra)
        return r

    print(
        f"Agent Loop started | level={current_level} | "
        f"max_turns={max_turns} | max_time={max_time}s"
    )
    if resume_state:
        print(
            f"Agent Loop resumed | completed={len(completed_steps)} | "
            f"elapsed_before={elapsed_before:.1f}s"
        )

    # ---- main loop ----
    while iteration < max_turns:
        # Kill switch
        if context.get("cancelled"):
            print("Agent Loop: kill switch activated")
            final = results[-1] if results else "נעצר."
            _print_loop_summary(completed_steps, escalations, total_elapsed())
            return make_result(final, stopped=True)

        # Time governor
        if total_elapsed() > max_time:
            print(f"Agent Loop: time limit reached ({max_time}s)")
            break

        # ---- PLAN phase ----
        available_intents = _get_available_intents(current_level)
        planned_steps = await _plan_next_steps(
            message, completed_steps, available_intents, next_step_id, use_web,
        )
        if not planned_steps:
            print("Agent Loop: planner returned no steps, finishing")
            break

        # ---- EXECUTE phase ----
        for step in planned_steps:
            if context.get("cancelled"):
                break
            if total_elapsed() > max_time:
                break

            intent = step["intent"]
            required_level = INTENT_MIN_LEVEL.get(intent, 0)

            # Escalation gating
            if required_level > current_level:
                if required_level <= approved_level + 1:
                    esc = {
                        "current_level": current_level,
                        "requested_level": required_level,
                        "reason": (
                            f"Step #{step['step_id']} ({intent}) "
                            f"requires level {required_level}"
                        ),
                    }
                    print(f"Escalation Proposal (auto-approved): {esc}")
                    current_level = required_level
                    escalations.append(esc)
                else:
                    # Pause loop — needs user approval
                    print(
                        f"Escalation blocked: step #{step['step_id']} "
                        f"needs level {required_level}"
                    )
                    proposed_plan = {
                        **plan,
                        "suggested_automation_level": required_level,
                    }
                    return make_result(
                        "",
                        needs_approval=True,
                        approval_request_text=(
                            "בזמן הביצוע נדרשת הרשאה גבוהה יותר.\n"
                            f"שלב #{step['step_id']} ({intent}) "
                            f"דורש Level {required_level}.\n"
                            f"רמה נוכחית: {current_level}.\n"
                            f"לאשר העלאה ל-Level {required_level}? "
                            "(כן / לא)"
                        ),
                        proposed_plan=proposed_plan,
                        resume_state={
                            "completed_steps": completed_steps,
                            "results": results,
                            "tools_used": tools_used,
                            "escalations": escalations,
                            "iteration": iteration,
                            "next_step_id": step["step_id"],
                            "elapsed_seconds": total_elapsed(),
                        },
                    )

            # Run step
            try:
                result_text = await _execute_step(
                    step, message, plan, current_level, results, memory_context,
                )
                step["status"] = "done"
                step["result_summary"] = (result_text or "")[:200]
                if result_text:
                    results.append(result_text)
            except Exception as e:
                step["status"] = "failed"
                step["result_summary"] = str(e)[:200]
                result_text = None

            completed_steps.append(step)

            for tool in step.get("tools", []):
                if tool not in tools_used:
                    tools_used.append(tool)

            print(
                f"STEP #{step['step_id']} | {intent} | "
                f"{step.get('tools', [])} | {step['status']}"
            )

            next_step_id = step["step_id"] + 1

            if intent == "finalize" and result_text:
                _print_loop_summary(completed_steps, escalations, total_elapsed())
                return make_result(result_text)

        # ---- OBSERVE / UPDATE: iteration done ----
        iteration += 1

    # Governor limit reached — compile what we have
    if results:
        compiled = await asyncio.to_thread(
            generate_fast,
            f"User request: {message}\n\n"
            "Gathered info:\n"
            + "\n---\n".join(results)
            + "\n\nCompile a final answer. "
            "Note: execution was limited by time/turn governors.",
        )
    else:
        compiled = (
            "הגעתי למגבלת הביצוע ולא הספקתי לאסוף מידע. "
            "נסה שוב עם governors גדולים יותר."
        )

    _print_loop_summary(completed_steps, escalations, total_elapsed())
    return make_result(compiled, stopped=True)


def _print_loop_summary(
    steps: list[dict], escalations: list[dict], elapsed: float,
) -> None:
    done = sum(1 for s in steps if s.get("status") == "done")
    failed = sum(1 for s in steps if s.get("status") == "failed")
    print(
        f"Agent Loop Summary: steps_done={done}, failed={failed}, "
        f"escalations={len(escalations)}, time={round(elapsed, 2)}s"
    )
