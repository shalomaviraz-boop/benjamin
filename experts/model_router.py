"""Task-aware provider routing for Benjamin."""
from __future__ import annotations

from experts.gemini_client import generate_fast, generate_web
from experts.gpt_client import GPTClient
from experts.claude_client import generate_claude_text
from utils.benjamin_identity import (
    build_benjamin_user_prompt,
    build_personal_synthesis_prompt,
)
from utils.logger import logger


WEB_UNAVAILABLE_MESSAGE = (
    "שליפה חיה מהווב לא זמינה לי כרגע, אז אני לא אענה מתוך ידע מיושן. "
    "תנסה שוב עוד כמה דקות או תבקש שאחפש בצורה אחרת."
)


def _is_ai_or_news(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in ["חדשות", "עדכון", "מה חדש", "news", "latest", "anthropic", "openai", "claude", "gemini", "gpt", "ai", "בינה מלאכותית"])


def _web_mode_from_task(task_type: str | None, message: str, plan: dict) -> str:
    if task_type == "finance":
        return "market"
    if task_type in {"research", "ai_expert"} and _is_ai_or_news(message):
        return "news"
    if plan.get("grounded_web") and _is_ai_or_news(message):
        return "news"
    if plan.get("use_web"):
        return "research"
    return "research"


def _looks_like_stale_cutoff(text: str) -> bool:
    """
    Detect the classic 'my knowledge ends on <date>, I can't give live info'
    fallback output. If the model returns this on a grounded_web query, we
    refuse it rather than pass a stale answer back to the user.
    """
    if not text:
        return True
    t = text.lower()
    tells = [
        "knowledge cutoff",
        "training data",
        "as of my last update",
        "i don't have access to real-time",
        "i do not have access to real-time",
        "i cannot browse",
        "up to april 2024",
        "up to 2024",
        "נכון למועד ה",
        "נכון לעדכון האחרון",
        "אין לי גישה למידע בזמן אמת",
        "המידע שלי מסתיים",
        "נכון לאפריל 2024",
    ]
    return any(tell in t for tell in tells)


class ModelRouter:
    def __init__(self):
        self.gpt = GPTClient()

    async def generate(self, *, message: str, plan: dict, memory_context: dict | None = None, force_provider: str | None = None) -> tuple[str, str]:
        task_type = str(plan.get("task_type") or "").strip()

        # Personal synthesis: self-reflective question. Compose a dynamic
        # synthesis prompt over the live memory context and answer in Claude
        # (or GPT fallback) — never hardcoded.
        if task_type == "personal_synthesis":
            synth_prompt = build_personal_synthesis_prompt(message, memory_context)
            try:
                text = await generate_claude_text(synth_prompt)
                if text and text.strip():
                    return text.strip(), "claude_personal_synthesis"
            except Exception as e:
                logger.warning(f"Claude personal_synthesis failed, trying GPT: {e}")
            try:
                text = await self.gpt.generate(synth_prompt)
                if text and text.strip():
                    return text.strip(), "gpt_personal_synthesis"
            except Exception as e:
                logger.warning(f"GPT personal_synthesis fallback failed: {e}")
            return "לא הצלחתי לענות עכשיו. נסה שוב.", "personal_synthesis_unavailable"

        provider = force_provider or self._pick_provider(message=message, task_type=task_type, plan=plan)
        prompt = build_benjamin_user_prompt(message, memory_context)

        if provider == "gemini_web":
            try:
                text = await generate_web(
                    prompt,
                    memory_context=memory_context,
                    web_mode=_web_mode_from_task(task_type, message, plan),
                )
            except Exception as e:
                logger.warning(f"Gemini web failed: {e}")
                text = ""

            text = (text or "").strip()

            # If the plan demands realtime grounding, we refuse to serve any
            # answer that smells like stale cutoff knowledge. Better a clear
            # "live retrieval unavailable" than a misleading stale answer.
            if plan.get("grounded_web") and (not text or _looks_like_stale_cutoff(text)):
                return WEB_UNAVAILABLE_MESSAGE, "web_unavailable"

            if not text:
                # Non-grounded use_web request: soft-fallback to GPT is OK.
                try:
                    text = await self.gpt.generate(prompt)
                except Exception as e:
                    logger.warning(f"GPT fallback after Gemini web failed: {e}")
                    text = ""
                return (text or "").strip() or "לא הצלחתי לענות עכשיו.", "gpt_fallback"

            return text, provider

        if provider == "claude":
            return await generate_claude_text(prompt), provider
        if provider == "gpt":
            return await self.gpt.generate(prompt), provider
        return await generate_fast(prompt, memory_context=memory_context), "gemini_fast"

    def _pick_provider(self, *, message: str, task_type: str, plan: dict) -> str:
        # Realtime grounding always beats other preferences.
        if plan.get("grounded_web") or plan.get("use_web"):
            return "gemini_web"
        if task_type in {"code", "relationships", "business_strategy"}:
            return "claude"
        if task_type in {"assistant", "fitness_health", "memory", "finance", "research", "ai_expert"}:
            return "gpt"
        return "gpt"
