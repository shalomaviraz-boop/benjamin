"""Gemini with Google Search for web-grounded answers."""
import asyncio
import os
import google.generativeai as genai

from utils.logger import logger
from utils.helpers import get_timestamp

MODELS = [
    "gemini-2.0-flash-exp",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
]


class GeminiWeb:
    """Gemini with Google Search grounding."""

    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

    async def search(self, query: str) -> dict:
        """Search with Gemini + Google Search, return content + metadata."""
        is_hebrew = any("\u0590" <= c <= "\u05FF" for c in query)

        if is_hebrew:
            prompt = f"חפש בגוגל ותן תשובה מדויקת:\n{query}\nתן עובדות + מקורות"
        else:
            prompt = f"Search Google and give accurate answer:\n{query}\nProvide facts + sources"

        for model_name in MODELS:
            try:
                # Try with google_search_retrieval tool (format varies by SDK version)
                try:
                    model = genai.GenerativeModel(
                        model_name,
                        tools=[{"google_search_retrieval": {}}],
                    )
                except (TypeError, ValueError):
                    model = genai.GenerativeModel(model_name)

                response = await asyncio.to_thread(model.generate_content, prompt)

                if not response.candidates:
                    raise ValueError("No candidates in response")

                text = response.text if hasattr(response, "text") else str(response)

                # Extract grounding metadata
                sources = []
                unique_domains = set()

                if hasattr(response, "candidates") and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, "grounding_metadata") and candidate.grounding_metadata:
                        grounding = candidate.grounding_metadata
                        if hasattr(grounding, "grounding_chunks"):
                            for chunk in grounding.grounding_chunks:
                                if hasattr(chunk, "web") and hasattr(chunk.web, "uri"):
                                    uri = chunk.web.uri
                                    sources.append(chunk)
                                    try:
                                        domain = uri.split("/")[2]
                                        unique_domains.add(domain)
                                    except IndexError:
                                        pass

                # Confidence by unique domains
                n_domains = len(unique_domains)
                if n_domains >= 3:
                    confidence = "high"
                elif n_domains >= 2:
                    confidence = "medium"
                elif n_domains == 1:
                    confidence = "low"
                else:
                    confidence = "uncertain"

                return {
                    "content": text,
                    "timestamp": get_timestamp(),
                    "confidence": confidence,
                    "sources_count": len(sources),
                    "unique_domains": n_domains,
                }

            except Exception as e:
                logger.warning(f"Gemini {model_name} search failed: {e}")
                continue

        raise Exception("All Gemini models failed for search")
