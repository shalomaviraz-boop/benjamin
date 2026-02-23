"""GPT = Orchestrator Brain. Returns structured execution plan with autonomy level."""
import json
import os

from openai import OpenAI

SYSTEM_PROMPT = """You are the routing brain of an AI super assistant.
You DO NOT answer the user.
You ONLY decide the execution plan.

Automation Levels (strict):
0 = No tools, no loops. Simple answer only. Greetings, static facts, general knowledge.
1 = Read-only tools: web search allowed. Current info: prices, weather, news, exchange rates.
2 = Quality layer: verification or code review by secondary model. Important answers, code generation.
3 = Agent loop (limited): task decomposition, refinement passes, limited multi-step.
4 = Semi-autonomous: multi-model, extended loops. Requires governors.
5 = Fully autonomous: subtasks, multiple loops. Requires governors + kill switch.

Decision rules:
- Simple greetings, static knowledge, harmless conversation → level 0
- Needs current/live data (prices, weather, news, "what is X right now") → level 1, use_web=true
- Code generation or technical implementation → level 2, require_code_review=true
- High-stakes topics requiring verification → level 2, require_verification=true, use_web=true
- Multi-step tasks, complex analysis, decomposition needed → level 3, require_task_decomposition=true
- Large research or project-level tasks → level 4-5

Verification triggers (require_verification=true):
- Financial transactions: transfer, invest, trade, buy, sell, העברה, השקעה, מסחר
- Legal actions
- Medical treatment or diagnosis
- Step-by-step execution: "איך לבצע", "תן לי שלבים", "how to execute"
- Irreversible: delete, cancel, transfer money, מחיקה, ביטול
- Money movement
- Verification requests: "תן לי מקורות", "בדוק", "אמת", "אימות", "האם נכון", "verify", "fact check"

Memory suggestion (suggest_memory_write):
- Set suggest_memory_write=true when the user message contains stable personal info worth remembering:
  name, age, job, preferences, contact info, project names, important dates, etc.
- If message starts with "תזכור" / "remember" → suggest_memory_write=true and fill memory_to_write:
  type="fact", key=short topic (e.g. "name"), value=the fact text.
- Otherwise, if you detect personal info → suggest_memory_write=true, memory_to_write=null (handler will extract).

execution_mode:
- "direct" for level 0-2
- "agent_loop" for level 3-5

Governor requirements:
- Level 4-5 MUST include governors: max_budget_usd, max_turns, max_execution_time_seconds
- Level 0-3: governors optional

If unsure about level → choose 1.
If unsure about use_web → set true.

Return ONLY valid JSON."""

USER_PROMPT_TEMPLATE = """{memory_block}Message: {message}

Return JSON with:
- suggested_automation_level (integer 0-5)
- execution_mode ("direct" or "agent_loop")
- tools_required (string array, e.g. ["web_search","verification","code_review"])
- use_web (bool)
- require_verification (bool)
- require_code_review (bool)
- require_task_decomposition (bool)
- suggest_memory_write (bool)
- memory_to_write (object or null: {{"type":"fact","key":"...","value":"..."}})
- governors (object with optional: max_budget_usd, max_turns, max_execution_time_seconds)
- reason (short string)
No other text."""


def _format_memory_context(memory_context: dict | None) -> str:
    """Format memory for router prompt: profile (max 10 lines), memories (max 8), project (max 10)."""
    if not memory_context:
        return ""
    lines = []
    profile = memory_context.get("user_profile") or {}
    if isinstance(profile, dict) and profile:
        profile_str = json.dumps(profile, ensure_ascii=False)
        for line in profile_str.split("\n")[:10]:
            if line.strip():
                lines.append(f"[Profile] {line.strip()}")
    memories = memory_context.get("relevant_memories") or []
    for m in memories[:8]:
        if isinstance(m, dict):
            k = m.get("key", "")
            v = m.get("value", "")[:80]
            lines.append(f"[Memory] {k}: {v}")
        elif isinstance(m, str):
            lines.append(f"[Memory] {m}")
    state = memory_context.get("project_state") or {}
    if isinstance(state, dict) and state:
        state_str = json.dumps(state, ensure_ascii=False)
        for line in state_str.split("\n")[:10]:
            if line.strip():
                lines.append(f"[Project] {line.strip()}")
    if not lines:
        return ""
    return "Context about user:\n" + "\n".join(lines) + "\n\n"


def decide(message: str, memory_context: dict | None = None) -> dict:
    """Returns structured execution plan. Injects memory into prompt if provided."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    memory_block = _format_memory_context(memory_context)
    user_content = USER_PROMPT_TEMPLATE.format(
        memory_block=memory_block,
        message=message,
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
    )
    text = response.choices[0].message.content.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    plan = json.loads(text)

    plan.setdefault("suggested_automation_level", 0)
    plan.setdefault("execution_mode", "direct")
    plan.setdefault("tools_required", [])
    plan.setdefault("use_web", False)
    plan.setdefault("require_verification", False)
    plan.setdefault("require_code_review", False)
    plan.setdefault("require_task_decomposition", False)
    plan.setdefault("suggest_memory_write", False)
    plan.setdefault("memory_to_write", None)
    plan.setdefault("governors", {})
    plan.setdefault("reason", "")

    level = plan["suggested_automation_level"]
    if level >= 4:
        gov = plan["governors"]
        gov.setdefault("max_budget_usd", 0.50)
        gov.setdefault("max_turns", 10)
        gov.setdefault("max_execution_time_seconds", 120)

    return plan
