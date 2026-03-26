"""First-version verification agent for validating execution output."""

from agents.agent_context import read_shared_context
from agents.base_agent import BaseAgent
from experts.claude_client import review_and_improve_code, sanity_check_answer


class VerificationAgent(BaseAgent):
    def __init__(self):
        super().__init__("verification", "Validates and optionally revises draft outputs.")

    async def run(self, task: dict, context: dict) -> dict:
        shared = read_shared_context(task, context)
        message = (shared.user_message or task.get("message") or task.get("original_message") or "").strip()
        draft_output = (
            shared.execution_output.get("output")
            or task.get("draft_output")
            or task.get("output")
            or ""
        ).strip()
        plan = shared.task or task.get("plan") or {}

        if not draft_output:
            result = {
                "approved": False,
                "output": "",
                "notes": "verification failed: missing draft output",
                "needs_revision": True,
            }
            shared.verification_output = result
            shared.add_log(self.name, "failed: missing draft output")
            result["agent_context"] = shared.to_dict()
            return result

        try:
            if plan.get("require_code_review"):
                reviewed = await review_and_improve_code(draft_output, message)
            else:
                reviewed = await sanity_check_answer(draft_output, message, None)
        except Exception as e:
            result = {
                "approved": False,
                "output": draft_output,
                "notes": f"verification failed: {e}",
                "needs_revision": True,
            }
            shared.verification_output = result
            shared.add_log(self.name, f"failed: {e}")
            result["agent_context"] = shared.to_dict()
            return result

        revised = (reviewed or "").strip()
        if not revised:
            result = {
                "approved": False,
                "output": draft_output,
                "notes": "verification failed: empty verifier output",
                "needs_revision": True,
            }
            shared.verification_output = result
            shared.add_log(self.name, "failed: empty verifier output")
            result["agent_context"] = shared.to_dict()
            return result

        if revised == draft_output:
            result = {
                "approved": True,
                "output": draft_output,
                "notes": "approved as-is",
                "needs_revision": False,
            }
            shared.verification_output = result
            shared.final_output = draft_output
            shared.add_log(self.name, "approved as-is")
            result["agent_context"] = shared.to_dict()
            return result

        result = {
            "approved": True,
            "output": revised,
            "notes": "small revision applied by verifier",
            "needs_revision": True,
        }
        shared.verification_output = result
        shared.final_output = revised
        shared.add_log(self.name, "approved with small revision")
        result["agent_context"] = shared.to_dict()
        return result
