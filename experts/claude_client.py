"""Claude client for code writing and review."""
import os
from anthropic import AsyncAnthropic

from utils.logger import logger

MODELS = [
    "claude-sonnet-4-20250514",
    "claude-3-5-sonnet-20241022",
]


def _extract_text(response) -> str:
    """Extract text from Claude response."""
    if hasattr(response, "content") and response.content:
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
    return ""


class ClaudeClient:
    """Claude client for code and review."""

    def __init__(self):
        self.client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    async def write_code(self, task: str, fix_issues: list[str] | None = None) -> str:
        """Write or fix Python code."""
        if fix_issues:
            prompt = f"""Fix this code:

Original task: {task}

Issues to fix:
{chr(10).join(f"- {issue}" for issue in fix_issues)}

Provide corrected code with:
- Type hints
- Docstrings
- Error handling
"""
        else:
            prompt = f"""Write Python code for: {task}

Requirements:
- Clean, working code
- Type hints
- Docstrings
- Error handling
"""

        for model_name in MODELS:
            try:
                response = await self.client.messages.create(
                    model=model_name,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                )
                return _extract_text(response)
            except Exception as e:
                logger.warning(f"Claude {model_name} write_code failed: {e}")
                continue

        raise Exception("All Claude models failed for write_code")

    async def review_code(self, code: str) -> str:
        """Review code - find 3 potential failures and 3 tests (DIFFERENT prompt!)."""
        prompt = f"""Code Review - find real issues:
```python
{code}
```

Provide exactly:
1. **3 נקודות כשל אפשריות** (potential failures)
2. **3 בדיקות שצריך לעשות** (tests to run)

Be critical. Find real issues, not style.
"""

        for model_name in MODELS:
            try:
                response = await self.client.messages.create(
                    model=model_name,
                    max_tokens=2048,
                    messages=[{"role": "user", "content": prompt}],
                )
                return _extract_text(response)
            except Exception as e:
                logger.warning(f"Claude {model_name} review_code failed: {e}")
                continue

        raise Exception("All Claude models failed for review_code")

    async def review_advice(self, question: str, response: str) -> str:
        """Review advice/response for high-risk questions."""
        prompt = f"""Review this advice for potential issues:

Original question: {question}

Response: {response}

Find 2-3 potential risks or things to double-check.
Be concise. Write in same language as question.
"""

        for model_name in MODELS:
            try:
                api_response = await self.client.messages.create(
                    model=model_name,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                )
                return _extract_text(api_response)
            except Exception as e:
                logger.warning(f"Claude {model_name} review_advice failed: {e}")
                continue

        raise Exception("All Claude models failed for review_advice")
