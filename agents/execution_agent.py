"""Execution agent using Benjamin provider routing."""
from __future__ import annotations

from agents.agent_context import read_shared_context
from agents.agent_contract import build_agent_result
from agents.base_agent import BaseAgent
from experts.model_router import ModelRouter


class ExecutionAgent(BaseAgent):
    def __init__(self):
        super().__init__("execution", "Executes task prompts using Benjamin provider routing.")
        self.model_router = ModelRouter()

    async def run(self, task: dict, context: dict) -> dict:
        shared = read_shared_context(task, context)
        message = (shared.user_message or task.get("message") or "").strip()
        plan = shared.task or task.get("plan") or {}
        memory_context = shared.memory_context or (context or {}).get("memory_context")

        if not message:
            return build_agent_result(
                agent=self.name,
                status="failed",
                notes="missing task message",
                should_fallback=True,
                agent_context=shared.to_dict(),
            )

        try:
            output, provider = await self.model_router.generate(
                message=message,
                plan=plan,
                memory_context=memory_context,
            )
            result = build_agent_result(
                agent=self.name,
                output=output,
                notes=f"provider={provider}",
                agent_context=shared.to_dict(),
            )
            shared.execution_output = result
            shared.final_output = output
            shared.add_log(self.name, f"execution success ({provider})")
            result["agent_context"] = shared.to_dict()
            return result
        except Exception as e:
            result = build_agent_result(
                agent=self.name,
                status="failed",
                notes=f"execution error: {e}",
                should_fallback=True,
                agent_context=shared.to_dict(),
            )
            shared.execution_output = result
            shared.add_log(self.name, f"execution failed: {e}")
            result["agent_context"] = shared.to_dict()
            return result
