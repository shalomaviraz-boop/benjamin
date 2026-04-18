"""Minimal base contract for internal Benjamin agents."""

from agents.agent_capabilities import DEFAULT_AGENT_CAPABILITIES


class BaseAgent:
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.capabilities = DEFAULT_AGENT_CAPABILITIES.get(name, {
            "description": description,
            "can_handle": [],
            "tools_required": [],
            "read_only": True,
            "write_capable": False,
        })

    async def run(self, task: dict, context: dict) -> dict:
        raise NotImplementedError(f"{self.name} does not implement run()")
