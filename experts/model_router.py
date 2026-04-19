"""Task-aware provider routing.

Architecture:
    Gemini = scout (web search / retrieval)
    GPT    = captain (final user-facing composer for nuanced replies)
    Claude = strategist (deep reasoning / verification / code review)

For nuanced personal / financial / strategic / relational replies that need
fresh data, the router runs a two-step pipeline:
    1. gemini_web gathers evidence
    2. gpt composes the final user-facing answer over that evidence + memory + persona
"""

from __future__ import annotations

import os

from openai import AsyncOpenAI

from experts.claude_client import generate_reasoning
from experts.gemini_client import generate_fast, generate_web
from memory.memory_store import format_memory_for_prompt
from utils.output_sanitizer import sanitize_user_facing_text

OPENAI_REPLY_MODEL = os.getenv("BENJAMIN_GPT_REPLY_MODEL", "gpt-4o-mini")

# Tasks where Gemini is allowed to be the FINAL responder (no nuance needed).
GEMINI_FINAL_OK = {"research", "ai_news"}

# Tasks where GPT MUST shape the final reply (nuanced personal/financial/strategy).
NUANCED_TASKS = {
    "assistant",
    "memory",
    "relationships",
    "fitness_health",
    "business_strategy",
    "ai_expert",
    "finance",
    "planning",
    "execution",
    "code",
}

_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY not set")
        _openai_client = AsyncOpenAI(api_key=key)
    return _openai_client


async def _generate_gpt(prompt: str, *, system_prompt: str | None = None, temperature: float = 0.35) -> str:
    client = _get_openai_client()
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    response = await client.chat.completions.create(
        model=OPENAI_REPLY_MODEL,
        temperature=temperature,
        messages=messages,
    )
    return (response.choices[0].message.content or "").strip()


def _inject_memory_for_non_gemini(prompt: str, memory_context: dict | None) -> str:
    context_block = format_memory_for_prompt(
        memory_context,
        detailed=False,
        include_conversation=True,
    )
    if not context_block:
        return prompt
    return context_block + "\n\n" + prompt


def _format_evidence(scout_text: str) -> str:
    cleaned = (scout_text or "").strip()
    if not cleaned:
        return ""
    return (
        "## Web Scout Evidence (from Gemini search; treat as raw notes, not as final tone)\n"
        f"{cleaned[:4000]}\n"
        "## End Evidence"
    )


def _composer_system_prompt() -> str:
    return (
        "אתה בנימין: chief-of-staff אישי. אתה מקבל ראיות גולמיות מסקאוט (Gemini) וזיכרון אישי על מתן.\n"
        "תפקידך: לכתוב תשובה אחת חדה, אישית, מדויקת, בטון של מתן.\n"
        "חוקים מחייבים:\n"
        "- אל תעתיק את הראיות ישירות. סנן, חתוך, וסכם רק מה שרלוונטי לשאלה.\n"
        "- אל תוסיף מקורות, לינקים גולמיים או הערות שוליים [1].\n"
        "- אל תפתח ב'להלן' / 'הנה גרסה' / 'לסיכום' / 'נכון ל...' / 'intelligence report'.\n"
        "- אם בשאלת המשך יש 'זה' / 'this' / 'איך זה ישפיע' — תפתור את ההפניה רק לפי השיחה האחרונה. אל תזרום לנושא ישן.\n"
        "- אם הראיות חלשות או לא ודאיות — תגיד זאת בקצרה במקום להמציא.\n"
        "- בלי בלה-בלה. תשובה אישית, חדה, פרקטית."
    )


async def _scout_then_compose(
    *,
    prompt: str,
    memory_context: dict | None,
    web_mode: str,
    system_prompt: str | None,
) -> tuple[str, str]:
    """Gemini gathers evidence, GPT composes final reply with persona + memory + evidence."""
    scout_text = ""
    scout_error = ""
    try:
        scout_text = await generate_web(prompt, memory_context=None, web_mode=web_mode)
    except Exception as exc:
        scout_error = str(exc)

    evidence = _format_evidence(scout_text)
    composer_input_parts = [_inject_memory_for_non_gemini(prompt, memory_context)]
    if evidence:
        composer_input_parts.append(evidence)
    elif scout_error:
        composer_input_parts.append(f"## Web Scout Note\nAuto-search failed: {scout_error[:200]}\nGround the answer only in stable knowledge or say so.")
    composer_prompt = "\n\n".join(composer_input_parts)

    composed = await _generate_gpt(
        composer_prompt,
        system_prompt=system_prompt or _composer_system_prompt(),
    )
    return composed, "gpt+gemini_web"


class ModelRouter:
    """Pick the best provider for the task, then fail over conservatively."""

    def _provider_order(
        self,
        *,
        task_type: str,
        use_web: bool,
        require_code_review: bool,
        require_verification: bool,
    ) -> list[str]:
        if require_code_review or task_type == "code":
            return ["claude", "gpt", "gemini_fast"]
        if use_web and task_type in GEMINI_FINAL_OK:
            return ["gemini_web", "scout_then_compose", "gpt"]
        if use_web:
            # Web needed for nuanced task -> Gemini scout, GPT composes final voice.
            return ["scout_then_compose", "gpt", "claude"]
        if require_verification or task_type in {"business_strategy", "ai_expert"}:
            return ["claude", "gpt", "gemini_fast"]
        if task_type in {"assistant", "memory", "relationships", "fitness_health"}:
            return ["gpt", "claude", "gemini_fast"]
        if task_type in {"planning", "execution"}:
            return ["gpt", "claude", "gemini_fast"]
        return ["gpt", "claude", "gemini_fast"]

    async def generate(
        self,
        *,
        prompt: str,
        task_type: str,
        memory_context: dict | None = None,
        use_web: bool = False,
        require_code_review: bool = False,
        require_verification: bool = False,
        web_mode: str = "research",
        system_prompt: str | None = None,
    ) -> tuple[str, str]:
        providers = self._provider_order(
            task_type=task_type,
            use_web=use_web,
            require_code_review=require_code_review,
            require_verification=require_verification,
        )
        errors: list[str] = []

        for provider in providers:
            try:
                text = await self._call_provider(
                    provider=provider,
                    prompt=prompt,
                    memory_context=memory_context,
                    web_mode=web_mode,
                    system_prompt=system_prompt,
                )
                if text and text.strip():
                    cleaned = sanitize_user_facing_text(text.strip())
                    return cleaned, provider
                errors.append(f"{provider}:empty")
            except Exception as exc:
                errors.append(f"{provider}:{exc}")

        raise RuntimeError("all providers failed: " + " | ".join(errors))

    async def _call_provider(
        self,
        *,
        provider: str,
        prompt: str,
        memory_context: dict | None,
        web_mode: str,
        system_prompt: str | None,
    ) -> str:
        if provider == "scout_then_compose":
            text, _ = await _scout_then_compose(
                prompt=prompt,
                memory_context=memory_context,
                web_mode=web_mode,
                system_prompt=system_prompt,
            )
            return text
        if provider == "gemini_web":
            return await generate_web(prompt, memory_context=memory_context, web_mode=web_mode)
        if provider == "gemini_fast":
            return await generate_fast(prompt, memory_context=memory_context)
        if provider == "gpt":
            return await _generate_gpt(
                _inject_memory_for_non_gemini(prompt, memory_context),
                system_prompt=system_prompt,
            )
        if provider == "claude":
            return await generate_reasoning(
                _inject_memory_for_non_gemini(prompt, memory_context),
                system_prompt=system_prompt,
            )
        raise ValueError(f"Unknown provider: {provider}")


model_router = ModelRouter()
