"""P1: Gemini Fast - plain generate_content. No GPT, no Voice Pass."""
import asyncio

from experts.gemini_client import generate_fast

FAST_MODEL = "gemini-3-flash-preview"


async def run(message: str) -> str:
    """P1 → client.models.generate_content(model=FAST_MODEL, contents=message) → response.text"""
    return await asyncio.to_thread(generate_fast, message)
