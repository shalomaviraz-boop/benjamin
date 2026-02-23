"""GPT-4 client for orchestration, sanity check, and voice pass."""
import json
import os
from openai import AsyncOpenAI

from utils.logger import logger

MODELS = [
    "gpt-4o",
    "gpt-4-turbo",
]


class GPTClient:
    """GPT client for routing, sanity check, and voice pass."""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def decide_pipeline(self, message: str, context: str = "") -> dict:
        """Decide which pipeline to use for the message."""
        prompt = f"""Analyze and decide pipeline:

P1 (Direct): שאלות שהתשובה לא תשתנה לעולם
P2 (Web): עדכניות/עובדות/רגולציה - ספק → P2!
P3 (Reasoning): החלטות, ניתוח
P4 (Code): קוד

Message: {message}
Context: {context}

Return JSON only:
{{"pipeline": "p1|p2|p3|p4", "reasoning": "..."}}
"""

        for model_name in MODELS:
            try:
                response = await self.client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You decide pipelines. Return only JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                )
                text = response.choices[0].message.content.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                return json.loads(text)
            except Exception as e:
                logger.warning(f"GPT {model_name} decide_pipeline failed: {e}")
                continue

        raise Exception("All GPT models failed for decide_pipeline")

    async def generate(self, prompt: str) -> str:
        """Generate direct answer."""
        for model_name in MODELS:
            try:
                response = await self.client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.5,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"GPT {model_name} generate failed: {e}")
                continue

        raise Exception("All GPT models failed for generate")

    async def sanity_check(self, code: str, task: str) -> str:
        """Check if code solves the task correctly."""
        prompt = f"""Review code:
```python
{code}
```

Task: {task}

Check:
1. Solves task correctly?
2. Any bugs?
3. Safe to run?

Format:
VERDICT: YES/NO
ISSUES: [list 1-3 specific issues if NO, or "None"]
"""

        for model_name in MODELS:
            try:
                response = await self.client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"GPT {model_name} sanity_check failed: {e}")
                continue

        raise Exception("All GPT models failed for sanity_check")

    async def voice_pass(self, content: str, expert_name: str = "", review: str = "") -> str:
        """Final voice pass - make content sound natural and consistent."""
        review_part = f"\nReview: {review}" if review else ""
        prompt = f"""You are Benjamin's voice.

Content from {expert_name}:
{content}
{review_part}

Your job:
✅ Align style (friendly, clear, natural)
✅ Check contradictions
✅ Ensure it answers the question
❌ DO NOT summarize/shorten
❌ DO NOT remove important details
❌ DO NOT change facts
❌ DO NOT add follow-up questions
❌ DO NOT add small talk

Just answer directly. Keep ALL info from expert.

If content has timestamp/confidence - KEEP THEM!
"""

        for model_name in MODELS:
            try:
                response = await self.client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.5,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"GPT {model_name} voice_pass failed: {e}")
                continue

        raise Exception("All GPT models failed for voice_pass")
