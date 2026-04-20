"""GPT client for Benjamin final voice."""
from __future__ import annotations

import os
from openai import AsyncOpenAI

MODELS = [
    os.getenv("GPT_RESPONSE_MODEL", "gpt-4.1"),
    "gpt-4o",
]


class GPTClient:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def generate(self, prompt: str) -> str:
        last_error = None
        for model_name in MODELS:
            try:
                response = await self.client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "Answer as Benjamin: concise, sharp, natural Hebrew unless requested otherwise."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.4,
                )
                return (response.choices[0].message.content or "").strip()
            except Exception as e:
                last_error = e
                continue
        raise Exception(f"All GPT models failed for generate: {last_error}")
