from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from config import Settings
from learning import LearningEngine, LearningResult
from memory import SQLiteMemoryStore
from prompts import build_judgment_input, build_response_input, format_conversation, format_memories
from user_model import render_user_model


logger = logging.getLogger(__name__)


class JudgmentResult(BaseModel):
    intent: Literal["facts", "advice", "reflection", "strategy", "emotion", "update", "mixed", "other"]
    response_depth: Literal["short", "balanced", "deep"]
    style: Literal["direct", "soft", "warm", "sharp", "strategic", "mixed"]
    likely_need: str
    useful_truth: str
    avoid: list[str] = Field(default_factory=list)
    use_memory: bool = True
    needs_live_data: bool = False
    reasoning_effort: Literal["low", "medium", "high"] = "medium"


class BenjaminBrain:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.memory = SQLiteMemoryStore(settings.database_path, primary_user_id=settings.primary_user_id)
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.learning_engine = LearningEngine(
            client=self.client,
            model=settings.openai_analysis_model,
            timeout_seconds=settings.openai_timeout_seconds,
        )

    async def ensure_user_profile(self, user_id: str, display_name: str | None = None) -> dict[str, Any]:
        canonical_user_id = self._canonical_user_id(user_id)
        return await asyncio.to_thread(self.memory.ensure_user, canonical_user_id, display_name)

    async def reply(self, *, user_id: str, display_name: str | None, message_text: str) -> str:
        canonical_user_id = self._canonical_user_id(user_id)
        profile = await self.ensure_user_profile(canonical_user_id, display_name)
        await asyncio.to_thread(
            self.memory.log_conversation,
            canonical_user_id,
            "user",
            message_text,
            metadata={"display_name": display_name or "", "telegram_user_id": user_id},
        )

        recent_conversation = await asyncio.to_thread(
            self.memory.get_recent_conversation,
            canonical_user_id,
            limit=self.settings.recent_conversation_limit,
        )
        relevant_memories = await asyncio.to_thread(
            self.memory.retrieve_relevant_memories,
            canonical_user_id,
            message_text,
            limit=self.settings.relevant_memory_limit,
            scan_limit=self.settings.max_memories_to_scan,
        )

        profile_summary = render_user_model(profile)
        memory_lines = format_memories(relevant_memories)
        conversation_text = format_conversation(recent_conversation)

        judgment = await asyncio.to_thread(
            self._judge,
            profile_summary,
            memory_lines,
            conversation_text,
            message_text,
        )

        response_text = await asyncio.to_thread(
            self._generate_response,
            profile_summary,
            memory_lines,
            conversation_text,
            judgment,
            message_text,
        )

        await asyncio.to_thread(
            self.memory.log_conversation,
            canonical_user_id,
            "assistant",
            response_text,
            metadata={"judgment": judgment.model_dump()},
        )

        learning = await asyncio.to_thread(
            self.learning_engine.learn,
            profile_summary=profile_summary,
            recent_conversation=conversation_text,
            message_text=message_text,
            assistant_response=response_text,
        )
        await asyncio.to_thread(self._apply_learning, canonical_user_id, learning)

        return response_text

    def _canonical_user_id(self, user_id: str) -> str:
        if self.settings.single_user_mode:
            return self.settings.primary_user_id
        return user_id

    def _judge(
        self,
        profile_summary: str,
        memory_lines: str,
        conversation_text: str,
        message_text: str,
    ) -> JudgmentResult:
        try:
            response = self.client.with_options(timeout=self.settings.openai_timeout_seconds).responses.parse(
                model=self.settings.openai_analysis_model,
                reasoning={"effort": "low"},
                input=build_judgment_input(
                    profile_summary=profile_summary,
                    memories=memory_lines,
                    recent_conversation=conversation_text,
                    message_text=message_text,
                ),
                text_format=JudgmentResult,
            )
            parsed = response.output_parsed
            if parsed:
                return parsed
        except Exception as exc:
            logger.warning("Judgment parsing failed, falling back to heuristics: %s", exc)
        return self._heuristic_judgment(message_text)

    def _generate_response(
        self,
        profile_summary: str,
        memory_lines: str,
        conversation_text: str,
        judgment: JudgmentResult,
        message_text: str,
    ) -> str:
        response = self.client.with_options(timeout=self.settings.openai_timeout_seconds).responses.create(
            model=self.settings.openai_model,
            reasoning={"effort": judgment.reasoning_effort},
            input=build_response_input(
                profile_summary=profile_summary,
                memory_lines=memory_lines,
                recent_conversation=conversation_text,
                judgment=judgment.model_dump(),
                message_text=message_text,
            ),
            max_output_tokens=900,
        )
        text = (response.output_text or "").strip()
        if text:
            return text
        raise RuntimeError("OpenAI returned an empty response")

    def _apply_learning(self, user_id: str, learning: LearningResult) -> None:
        profile_updates = self._compact_structure(learning.profile_updates.model_dump(exclude_none=True))
        if profile_updates:
            self.memory.update_user_model(user_id, profile_updates)

        for memory in learning.memories:
            if memory.confidence < 0.55:
                continue
            self.memory.save_memory(
                user_id,
                memory.category,
                memory.content,
                key=memory.key,
                confidence=memory.confidence,
                importance=memory.importance,
            )

    def _compact_structure(self, value: Any) -> Any:
        if isinstance(value, dict):
            compacted = {}
            for key, item in value.items():
                cleaned = self._compact_structure(item)
                if cleaned in (None, "", [], {}):
                    continue
                compacted[key] = cleaned
            return compacted
        if isinstance(value, list):
            compacted_list = []
            for item in value:
                cleaned = self._compact_structure(item)
                if cleaned in (None, "", [], {}):
                    continue
                compacted_list.append(cleaned)
            return compacted_list
        return value

    def _heuristic_judgment(self, message_text: str) -> JudgmentResult:
        stripped = message_text.strip()
        lowered = stripped.casefold()
        intent = "other"
        if "?" in stripped or lowered.startswith(("what ", "why ", "how ", "מה ", "למה ", "איך ")):
            intent = "facts"
        if any(token in lowered for token in ["should i", "what should", "מה כדאי", "איך נכון", "strategy", "plan"]):
            intent = "strategy"
        if any(token in lowered for token in ["feel", "רגיש", "כואב", "קשה לי", "מפחד", "sad", "anxious"]):
            intent = "emotion"
        if any(token in lowered for token in ["think about me", "מי אני", "מה אתה יודע", "איך אתה רואה אותי"]):
            intent = "reflection"

        response_depth = "balanced"
        if len(stripped) < 50:
            response_depth = "short"
        if len(stripped) > 240 or intent in {"strategy", "reflection", "emotion"}:
            response_depth = "deep"

        style = "strategic" if intent in {"strategy", "reflection"} else "direct"
        if intent == "emotion":
            style = "warm"

        needs_live_data = any(
            token in lowered
            for token in ["today", "latest", "now", "currently", "news", "weather", "stock", "price", "היום", "עכשיו", "עדכני"]
        )

        useful_truth = "Be honest, cut fluff, and focus on the real decision or tension."
        likely_need = "clarity"
        if intent == "emotion":
            likely_need = "understanding plus grounded support"
            useful_truth = "Stability matters more than cleverness right now."
        if intent == "strategy":
            likely_need = "clear next-step strategy"
            useful_truth = "A concrete decision is more useful than more circling."

        reasoning_effort = "medium" if response_depth != "short" else "low"
        if intent in {"strategy", "reflection"} and response_depth == "deep":
            reasoning_effort = "high"

        return JudgmentResult(
            intent=intent,  # type: ignore[arg-type]
            response_depth=response_depth,  # type: ignore[arg-type]
            style=style,  # type: ignore[arg-type]
            likely_need=likely_need,
            useful_truth=useful_truth,
            avoid=["robotic phrasing", "generic advice"],
            use_memory=True,
            needs_live_data=needs_live_data,
            reasoning_effort=reasoning_effort,  # type: ignore[arg-type]
        )
