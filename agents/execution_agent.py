"""First-version execution agent for direct task execution."""

from agents.agent_context import read_shared_context
from agents.base_agent import BaseAgent
from experts.gemini_client import FAST_MODEL, generate_fast, generate_web


class ExecutionAgent(BaseAgent):
    def __init__(self):
        super().__init__("execution", "Executes task prompts using existing generation flow.")

    async def run(self, task: dict, context: dict) -> dict:
        shared = read_shared_context(task, context)
        message = (shared.user_message or task.get("message") or "").strip()
        plan = shared.task or task.get("plan") or {}
        memory_context = shared.memory_context or (context or {}).get("memory_context")
        use_web = bool(plan.get("use_web"))

        if not message:
            result = {
                "output": "",
                "status": "failed",
                "notes": "missing task message",
            }
            shared.execution_output = result
            shared.add_log(self.name, "missing task message")
            result["agent_context"] = shared.to_dict()
            return result

        try:
            if use_web:
                output = await generate_web(message, memory_context=memory_context)
            else:
                output = await generate_fast(message, memory_context=memory_context)
            result = {
                "output": output,
                "status": "success",
                "notes": f"model={FAST_MODEL}, use_web={use_web}",
            }
            shared.execution_output = result
            shared.final_output = output
            shared.add_log(self.name, f"execution success (use_web={use_web})")
            result["agent_context"] = shared.to_dict()
            return result
        except Exception as e:
            result = {
                "output": "",
                "status": "failed",
                "notes": f"execution error: {e}",
            }
            shared.execution_output = result
            shared.add_log(self.name, f"execution failed: {e}")
            result["agent_context"] = shared.to_dict()
            return result
