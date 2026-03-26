"""Shared agent context contract for Benjamin internal orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AgentContextState:
    task: dict = field(default_factory=dict)
    user_message: str = ""
    memory_context: dict = field(default_factory=dict)
    planning_output: dict = field(default_factory=dict)
    research_output: dict = field(default_factory=dict)
    execution_output: dict = field(default_factory=dict)
    verification_output: dict = field(default_factory=dict)
    final_output: str = ""
    metadata: dict = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)

    def add_log(self, agent_name: str, message: str) -> None:
        self.logs.append(f"{agent_name}: {message}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "AgentContextState":
        if not isinstance(data, dict):
            return cls()
        return cls(
            task=data.get("task") if isinstance(data.get("task"), dict) else {},
            user_message=str(data.get("user_message") or ""),
            memory_context=data.get("memory_context") if isinstance(data.get("memory_context"), dict) else {},
            planning_output=data.get("planning_output") if isinstance(data.get("planning_output"), dict) else {},
            research_output=data.get("research_output") if isinstance(data.get("research_output"), dict) else {},
            execution_output=data.get("execution_output") if isinstance(data.get("execution_output"), dict) else {},
            verification_output=data.get("verification_output")
            if isinstance(data.get("verification_output"), dict)
            else {},
            final_output=str(data.get("final_output") or ""),
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
            logs=[str(x) for x in (data.get("logs") or []) if str(x).strip()],
        )


def read_shared_context(task: dict, context: dict) -> AgentContextState:
    raw = None
    if isinstance(task, dict):
        raw = task.get("agent_context")
    if raw is None and isinstance(context, dict):
        raw = context.get("agent_context")
    state = AgentContextState.from_dict(raw)

    if isinstance(context, dict) and isinstance(context.get("memory_context"), dict):
        # Keep compatibility with previous ad-hoc memory_context usage.
        state.memory_context = context["memory_context"]
    if isinstance(task, dict) and isinstance(task.get("plan"), dict) and not state.task:
        state.task = task["plan"]
    if isinstance(task, dict) and not state.user_message:
        state.user_message = str(task.get("message") or task.get("original_message") or "")
    return state
