"""Benjamin Core - Gemini only via google-genai. No OpenAI, no Claude."""
import os
import asyncio

from google import genai
from google.genai import types

FAST_MODEL = "gemini-3-flash-preview"
SEARCH_MODEL = "gemini-3-flash-preview"

_client = None


def get_client():
    """Create client once, reuse."""
    global _client
    if _client is None:
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY not set in .env")
        _client = genai.Client(api_key=key)
    return _client


def _inject_memory(contents: str, memory_context) -> str:
    """
    Inject structured memory into the prompt.
    memory_context may be a dict (preferred) or a string.
    """
    if not memory_context:
        return contents

    # If it's already a string, keep backward compatibility.
    if isinstance(memory_context, str):
        mem_block = f"# Memory Context\n{memory_context}"
        return f"{mem_block}\n\n{contents}"

    if not isinstance(memory_context, dict):
        mem_block = f"# Memory Context\n{str(memory_context)}"
        return f"{mem_block}\n\n{contents}"

    user_profile = memory_context.get("user_profile") or {}
    relevant_memories = memory_context.get("relevant_memories") or []
    recent_memories = memory_context.get("recent_memories") or []
    project_state = memory_context.get("project_state") or {}
    conversation_tail = memory_context.get("conversation_tail") or []

    lines: list[str] = []
    lines.append("# Memory Context")

    # Profile
    if isinstance(user_profile, dict) and user_profile:
        lines.append("## User Profile")
        for k, v in user_profile.items():
            if v is None:
                continue
            lines.append(f"- {k}: {v}")

    # Governor guidance (internal)
    governor = memory_context.get("governor") or {}
    if isinstance(governor, dict) and governor:
        lines.append("## Governor Guidance")
        il = governor.get("intervention_level")
        act = governor.get("recommended_action")
        ol = (governor.get("opening_line") or "").strip()
        sq = (governor.get("sharp_question") or "").strip()
        rp = governor.get("risk_pattern")
        sc = governor.get("alignment_score")
        lines.append(f"- alignment_score: {sc}")
        lines.append(f"- risk_pattern: {rp}")
        lines.append(f"- intervention_level: {il}")
        lines.append(f"- recommended_action: {act}")
        if ol:
            lines.append(f"- opening_line: {ol}")
        if sq:
            lines.append(f"- sharp_question: {sq}")

    # Conversation tail
    if isinstance(conversation_tail, list) and conversation_tail:
        lines.append("## Conversation (recent turns)")
        for m in conversation_tail[-15:]:
            if not isinstance(m, dict):
                continue
            role = (m.get("role") or "").strip() or "unknown"
            text = (m.get("content") or "").strip()
            if not text:
                continue
            # Keep it compact
            if len(text) > 800:
                text = text[:800].rstrip() + "…"
            lines.append(f"- {role}: {text}")

    # Relevant memories (semantic)
    if isinstance(relevant_memories, list) and relevant_memories:
        lines.append("## Relevant Memories")
        for mem in relevant_memories[:10]:
            if isinstance(mem, dict):
                key = (mem.get("key") or "").strip()
                val = mem.get("value")
                if key:
                    lines.append(f"- {key}: {val}")
                else:
                    lines.append(f"- {val}")
            else:
                lines.append(f"- {mem}")

    # Recent memories (last written)
    if isinstance(recent_memories, list) and recent_memories:
        lines.append("## Recent Memories")
        for mem in recent_memories[:10]:
            if isinstance(mem, dict):
                key = (mem.get("key") or "").strip()
                val = mem.get("value")
                if key:
                    lines.append(f"- {key}: {val}")
                else:
                    lines.append(f"- {val}")
            else:
                lines.append(f"- {mem}")

    # Project state
    if isinstance(project_state, dict) and project_state:
        lines.append("## Project State")
        for k, v in project_state.items():
            if v is None:
                continue
            lines.append(f"- {k}: {v}")

    mem_block = "\n".join(lines)
    return f"{mem_block}\n\n{contents}"


def _generate_fast_sync(contents: str) -> str:
    client = get_client()
    response = client.models.generate_content(
        model=FAST_MODEL,
        contents=contents,
    )
    return response.text or ""


def _generate_web_sync(contents: str) -> str:
    client = get_client()
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]
    )
    response = client.models.generate_content(
        model=SEARCH_MODEL,
        contents=contents,
        config=config,
    )
    return response.text or ""


async def generate_fast(
    contents: str,
    memory_context: str | None = None,
    **kwargs,
) -> str:
    """
    Async: Plain generate_content, no tools.
    Accepts extra kwargs for signature unification.
    """
    contents = _inject_memory(contents, memory_context)
    return await asyncio.to_thread(_generate_fast_sync, contents)


async def generate_web(
    contents: str,
    memory_context: str | None = None,
    **kwargs,
) -> str:
    """
    Async: generate_content with google_search tool.
    Accepts extra kwargs for signature unification.
    """
    contents = _inject_memory(contents, memory_context)
    return await asyncio.to_thread(_generate_web_sync, contents)