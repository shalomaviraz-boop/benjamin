"""Message handler - input validation, context, routing."""
from collections import deque

from orchestrator.benjamin_orchestrator import BenjaminOrchestrator


class BenjaminMessageHandler:
    """Handles incoming messages with context."""

    def __init__(self):
        self.orchestrator = BenjaminOrchestrator()
        self.context: dict[str, deque] = {}

    async def handle(self, message: str, user_id: str) -> str:
        """Handle incoming message."""
        if user_id not in self.context:
            self.context[user_id] = deque(maxlen=3)

        context_text = "\n".join(self.context[user_id])

        response = await self.orchestrator.route_and_execute(message, context_text)

        self.context[user_id].append(f"User: {message}\nAssistant: {response}")

        return response
