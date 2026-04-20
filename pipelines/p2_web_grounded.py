"""P2: Gemini Web - generate_content with google_search. No GPT, no Voice Pass."""
import asyncio

from experts.gemini_client import generate_web

SEARCH_MODEL = "gemini-3-flash-preview"


async def run(message: str) -> str:
    """P2 → generate_content with tools=[google_search] → response.text"""
    return await asyncio.to_thread(generate_web, message)
