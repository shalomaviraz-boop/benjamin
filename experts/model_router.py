"""Task-aware provider routing for Benjamin."""
from __future__ import annotations

from experts.gemini_client import generate_fast, generate_web
from experts.gpt_client import GPTClient
from experts.claude_client import generate_claude_text
from utils.benjamin_identity import build_benjamin_user_prompt


def _is_ai_or_news(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in ["חדשות", "עדכון", "מה חדש", "news", "latest", "anthropic", "openai", "claude", "gemini", "gpt", "ai", "בינה מלאכותית"])


def _web_mode_from_task(task_type: str | None, message: str, plan: dict) -> str:
    if task_type == "finance":
        return "market"
    if task_type in {"research", "ai_expert"} and _is_ai_or_news(message):
        return "news"
    if plan.get("use_web"):
        return "research"
    return "research"


class ModelRouter:
    def __init__(self):
        self.gpt = GPTClient()

    async def generate(self, *, message: str, plan: dict, memory_context: dict | None = None, force_provider: str | None = None) -> tuple[str, str]:
        task_type = str(plan.get("task_type") or "").strip()
        provider = force_provider or self._pick_provider(message=message, task_type=task_type, plan=plan)
        prompt = build_benjamin_user_prompt(message, memory_context)

        if provider == "gemini_web":
            return await generate_web(prompt, memory_context=memory_context, web_mode=_web_mode_from_task(task_type, message, plan)), provider
        if provider == "claude":
            return await generate_claude_text(prompt), provider
        if provider == "gpt":
            return await self.gpt.generate(prompt), provider
        return await generate_fast(prompt, memory_context=memory_context), "gemini_fast"

    def _pick_provider(self, *, message: str, task_type: str, plan: dict) -> str:
        if plan.get("use_web"):
            return "gemini_web"
        if task_type in {"code", "relationships", "business_strategy"}:
            return "claude"
        if task_type in {"assistant", "fitness_health", "memory", "finance", "research", "ai_expert"}:
            return "gpt"
        return "gpt"
