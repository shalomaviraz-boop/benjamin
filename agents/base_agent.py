"""Minimal base contract for internal Benjamin agents."""


class BaseAgent:
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description

    async def run(self, task: dict, context: dict) -> dict:
        raise NotImplementedError(f"{self.name} does not implement run()")
