"""Benjamin Core - Gemini only via google-genai. No OpenAI, no Claude."""
import os
import asyncio

genai = None
types = None

FAST_MODEL = "gemini-3-flash-preview"
SEARCH_MODEL = "gemini-3-flash-preview"


_client = None

WEB_MODE_PREFIXES = {
    "news": (
        "CRITICAL: This is a latest-news query. Use Google Search and return only current, recent, date-specific information. "
        "Do not rely on stale knowledge. Include explicit dates for each major item. Ignore old background unless directly needed."
    ),
    "market": (
        "CRITICAL: This is a market/current-status query. Use Google Search and return only current, date-specific information. "
        "Do not rely on stale knowledge. If data timing is unclear, say so explicitly."
    ),
    "research": (
        "Use Google Search when needed and prioritize up-to-date, source-backed information. "
        "If certainty is limited, say so explicitly."
    ),
}


def get_client():
    """Create client once, reuse."""
    global _client, genai, types
    if _client is None:
        if genai is None or types is None:
            from google import genai as _genai
            from google.genai import types as _types
            genai = _genai
            types = _types
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
    personal_model = memory_context.get("personal_model") or {}
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

    if isinstance(personal_model, dict) and personal_model:
        lines.append("## Personal Model")
        for k, v in personal_model.items():
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



def _extract_grounding_sources(response) -> list[str]:
    sources: list[str] = []

    try:
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            grounding = getattr(candidate, "grounding_metadata", None)
            if not grounding:
                continue

            chunks = getattr(grounding, "grounding_chunks", None) or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                if not web:
                    continue
                uri = getattr(web, "uri", None)
                if uri and uri not in sources:
                    sources.append(uri)
    except Exception:
        return sources

    return sources


def _generate_web_sync(contents: str, web_mode: str = "research") -> str:
    client = get_client()
    mode = (web_mode or "research").strip().lower()
    prefix = WEB_MODE_PREFIXES.get(mode, WEB_MODE_PREFIXES["research"])
    final_contents = f"{prefix}\n\n{contents}"

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]
    )
    response = client.models.generate_content(
        model=SEARCH_MODEL,
        contents=final_contents,
        config=config,
    )

    text = response.text or ""
    return text.strip()


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
    web_mode: str = "research",
    **kwargs,
) -> str:
    """
    Async: generate_content with google_search tool.
    Accepts extra kwargs for signature unification.
    """
    contents = _inject_memory(contents, memory_context)
    return await asyncio.to_thread(_generate_web_sync, contents, web_mode)