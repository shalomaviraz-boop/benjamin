from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from prompts import build_learning_input


class PreferencePatch(BaseModel):
    language: str | None = None
    response_style: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)


class ProfilePatch(BaseModel):
    name: str | None = None
    tendencies: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    struggles: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    relationship_context: list[str] = Field(default_factory=list)
    priorities: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    preferences: PreferencePatch = Field(default_factory=PreferencePatch)


class LearnedMemory(BaseModel):
    category: Literal[
        "identity",
        "goal",
        "preference",
        "struggle",
        "project",
        "important_conversation",
        "relationship_context",
        "priority",
        "interest",
        "value",
    ]
    content: str
    key: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    importance: float = Field(ge=0.0, le=1.0)


class LearningResult(BaseModel):
    profile_updates: ProfilePatch = Field(default_factory=ProfilePatch)
    memories: list[LearnedMemory] = Field(default_factory=list)


class LearningEngine:
    def __init__(self, client, model: str, timeout_seconds: float):
        self.client = client
        self.model = model
        self.timeout_seconds = timeout_seconds

    def learn(
        self,
        *,
        profile_summary: str,
        recent_conversation: str,
        message_text: str,
        assistant_response: str,
    ) -> LearningResult:
        try:
            response = self.client.with_options(timeout=self.timeout_seconds).responses.parse(
                model=self.model,
                reasoning={"effort": "low"},
                input=build_learning_input(
                    profile_summary=profile_summary,
                    recent_conversation=recent_conversation,
                    message_text=message_text,
                    assistant_response=assistant_response,
                ),
                text_format=LearningResult,
            )
            parsed = response.output_parsed
            if parsed:
                return parsed
        except Exception:
            pass
        return self._heuristic_learning(message_text)

    def _heuristic_learning(self, message_text: str) -> LearningResult:
        text = message_text.strip()
        lowered = text.casefold()
        result = LearningResult()

        goal_patterns = [
            r"אני רוצה\s+(.+)",
            r"i want to\s+(.+)",
            r"אני מחפש\s+(.+)",
            r"i'm looking for\s+(.+)",
        ]
        for pattern in goal_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                captured = match.group(1).strip(" .")
                if captured:
                    result.profile_updates.goals.append(captured)
                    result.memories.append(
                        LearnedMemory(
                            category="goal",
                            content=captured,
                            confidence=0.73,
                            importance=0.74,
                        )
                    )
                break

        project_patterns = [
            r"אני מתחיל\s+(.+)",
            r"i am starting\s+(.+)",
            r"i'm building\s+(.+)",
            r"אני בונה\s+(.+)",
        ]
        for pattern in project_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                captured = match.group(1).strip(" .")
                if captured:
                    result.profile_updates.projects.append(captured)
                    result.memories.append(
                        LearnedMemory(
                            category="project",
                            content=captured,
                            confidence=0.76,
                            importance=0.72,
                        )
                    )
                break

        if "מתלבט" in text or "can't decide" in lowered or "cannot decide" in lowered:
            result.profile_updates.struggles.append("currently dealing with indecision")
            result.memories.append(
                LearnedMemory(
                    category="struggle",
                    content="currently dealing with indecision around a meaningful issue",
                    confidence=0.62,
                    importance=0.58,
                )
            )

        if "אקסית" in text or "ex" in lowered:
            result.profile_updates.relationship_context.append("there is active emotional context involving an ex")
            result.memories.append(
                LearnedMemory(
                    category="relationship_context",
                    content="there is active emotional context involving an ex",
                    confidence=0.70,
                    importance=0.69,
                )
            )

        if "hebrew" in lowered or "עברית" in text:
            result.profile_updates.preferences.language = "Hebrew"
            result.memories.append(
                LearnedMemory(
                    category="preference",
                    content="prefers Hebrew communication",
                    confidence=0.83,
                    importance=0.67,
                )
            )

        if "direct" in lowered or "ישיר" in text:
            result.profile_updates.preferences.response_style.append("direct")
            result.memories.append(
                LearnedMemory(
                    category="preference",
                    content="prefers direct communication",
                    confidence=0.78,
                    importance=0.64,
                )
            )

        return result
