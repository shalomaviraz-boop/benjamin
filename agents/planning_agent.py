"""First-version planning agent for structured task plans."""

import json

from agents.agent_context import read_shared_context
from agents.agent_contract import build_agent_result
from agents.base_agent import BaseAgent
from experts.gemini_client import generate_fast


def _extract_json_object(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        data = json.loads(raw[start : end + 1])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class PlanningAgent(BaseAgent):
    def __init__(self):
        super().__init__("planning", "Breaks user requests into short execution plans.")

    async def run(self, task: dict, context: dict) -> dict:
        shared = read_shared_context(task, context)
        message = (shared.user_message or task.get("message") or "").strip()
        if not message:
            result = build_agent_result(
                agent=self.name,
                output="",
                notes="empty message, returning fallback plan",
                data={
                    "objective": "",
                    "steps": [],
                    "needs_research": False,
                    "needs_verification": False,
                    "recommended_agent_sequence": ["execution"],
                },
                agent_context=shared.to_dict(),
            )
            result.update(result["data"])
            shared.planning_output = result
            shared.add_log(self.name, "empty message, returning fallback plan")
            result["agent_context"] = shared.to_dict()
            return result

        prompt = (
            "You are a planning agent for Benjamin. Build a short practical plan.\n"
            "Return JSON only with this shape:\n"
            "{\n"
            '  "objective": "one short sentence",\n'
            '  "steps": ["step 1", "step 2"],\n'
            '  "needs_research": true/false,\n'
            '  "needs_verification": true/false,\n'
            '  "recommended_agent_sequence": ["research","execution","verification"]\n'
            "}\n"
            "Rules:\n"
            "- Keep 2-5 steps.\n"
            "- Be concise and concrete.\n"
            "- Use only these agent names in recommended_agent_sequence: research, memory, planning, execution, verification, code, finance, assistant, fitness_health, relationships, business_strategy, ai_expert.\n"
            f"- User task: {message}\n"
        )
        raw = await generate_fast(prompt)
        out = _extract_json_object(raw)

        steps = out.get("steps")
        if not isinstance(steps, list):
            steps = []
        steps = [str(s).strip() for s in steps if str(s).strip()][:5]
        if not steps:
            steps = ["Understand the request and constraints.", "Execute the task.", "Validate the result."]

        sequence = out.get("recommended_agent_sequence")
        if not isinstance(sequence, list):
            sequence = []
        allowed = {
            "research",
            "memory",
            "planning",
            "execution",
            "verification",
            "code",
            "finance",
            "assistant",
            "fitness_health",
            "relationships",
            "business_strategy",
            "ai_expert",
        }
        sequence = [str(s).strip() for s in sequence if str(s).strip() in allowed]
        if not sequence:
            sequence = ["execution"]

        payload = {
            "objective": str(out.get("objective") or message)[:220],
            "steps": steps,
            "needs_research": bool(out.get("needs_research")),
            "needs_verification": bool(out.get("needs_verification")),
            "recommended_agent_sequence": sequence,
        }
        result = build_agent_result(
            agent=self.name,
            output=payload["objective"],
            notes=f"planned {len(steps)} steps",
            data=payload,
            agent_context=shared.to_dict(),
        )
        result.update(payload)
        shared.planning_output = result
        shared.metadata["planning_needs_research"] = payload["needs_research"]
        shared.metadata["planning_needs_verification"] = payload["needs_verification"]
        shared.add_log(self.name, f"planned {len(steps)} steps")
        result["agent_context"] = shared.to_dict()
        return result
