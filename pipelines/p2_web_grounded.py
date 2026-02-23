"""P2: Web-grounded answer - Gemini Web → GPT Voice Pass."""
from experts.gemini_web import GeminiWeb
from experts.gpt_client import GPTClient

gemini = GeminiWeb()
gpt = GPTClient()


async def run(message: str) -> str:
    """P2: Web-grounded answer with GPT voice pass."""

    # 1. Gemini searches
    result = await gemini.search(message)

    # 2. GPT voice pass
    if result["confidence"] == "uncertain":
        voice_content = f"""Content from Gemini Web:
{result["content"]}

Confidence: UNCERTAIN (no reliable sources found)

You MUST tell user: "לא מצאתי מקור חד-משמעי לגבי..."
DO NOT make up answer!

Include timestamp: {result["timestamp"]}
"""
    else:
        voice_content = f"""Content from Gemini Web:
{result["content"]}

Timestamp: {result["timestamp"]}
Confidence: {result["confidence"]}
Sources: {result["sources_count"]} from {result["unique_domains"]} domains

Make this natural. Keep timestamp at end.
DO NOT remove any important details!
"""

    final = await gpt.voice_pass(voice_content, expert_name="Gemini Web")
    return final
