"""Task-aware provider routing with graceful multi-provider fallback."""

from __future__ import annotations

import os

from openai import AsyncOpenAI

from experts.claude_client import generate_reasoning
from experts.gemini_client import generate_fast, generate_web
from memory.memory_store import format_memory_for_prompt

OPENAI_REPLY_MODEL = os.getenv("BENJAMIN_GPT_REPLY_MODEL", "gpt-4o-mini")

_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY not set")
        _openai_client = AsyncOpenAI(api_key=key)
    return _openai_client


async def _generate_gpt(prompt: str, *, system_prompt: str | None = None) -> str:
    client = _get_openai_client()
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    response = await client.chat.completions.create(
        model=OPENAI_REPLY_MODEL,
        temperature=0.35,
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


class ModelRouter:
    """Pick the best provider for the task, then fail over conservatively."""

    def _provider_order(self, *, task_type: str, use_web: bool, require_code_review: bool, require_verification: bool) -> list[str]:
        if use_web or task_type in {"research", "finance"}:
            return ["gemini_web", "gpt", "claude"]
        if require_code_review or task_type == "code":
            return ["claude", "gpt", "gemini_fast"]
        if require_verification or task_type in {"business_strategy", "ai_expert"}:
            return ["claude", "gpt", "gemini_fast"]
        if task_type in {"assistant", "memory", "relationships", "fitness_health"}:
            return ["gpt", "gemini_fast", "claude"]
        if task_type in {"planning", "execution"}:
            return ["gpt", "claude", "gemini_fast"]
        return ["gpt", "gemini_fast", "claude"]

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
                if text.strip():
                    return text.strip(), provider
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
