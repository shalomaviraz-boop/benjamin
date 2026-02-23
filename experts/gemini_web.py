"""Gemini with Google Search for web-grounded answers. Uses google-genai SDK (AI Studio)."""
import asyncio
import os

from google import genai
from google.genai import types

from utils.logger import logger
from utils.helpers import get_timestamp

# Populated at startup from API - models that support generateContent
MODELS: list[str] = []

# Circuit breaker: return this instead of raising on quota errors
GEMINI_UNAVAILABLE_QUOTA = "GEMINI_UNAVAILABLE_QUOTA"


def _is_quota_error(e: Exception) -> bool:
    """Check if exception indicates quota/429 exhaustion."""
    err_str = str(e).lower()
    return (
        "429" in err_str
        or "resource_exhausted" in err_str
        or "limit: 0" in err_str
        or "quota" in err_str
        or "rate limit" in err_str
    )


def list_models() -> list[str]:
    """
    List models from AI Studio API. Log available models and supported methods.
    Returns models that support generateContent, preferring gemini-2.0-flash / gemini-1.5-flash.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")

    client = genai.Client(api_key=api_key)

    try:
        all_models = list(client.models.list())
    except Exception as e:
        if _is_quota_error(e):
            logger.warning(f"Gemini quota on list_models: {e}")
            return []
        raise RuntimeError(
            f"Failed to list Gemini models. Possible causes:\n"
            f"- API key mismatch: AI Studio key vs Vertex key (this SDK uses AI Studio)\n"
            f"- Invalid or expired API key from aistudio.google.com\n"
            f"Original error: {e}"
        ) from e

    supported: list[str] = []
    for model in all_models:
        name = getattr(model, "name", None) or ""
        actions = getattr(model, "supported_actions", None) or []
        if "generateContent" in actions:
            short_name = name.replace("models/", "") if name else ""
            if short_name:
                supported.append(short_name)
                logger.info(f"Gemini model available: {short_name} | supported_actions: {actions}")

    if not supported:
        if not all_models:
            return []  # Quota or empty - fallback to GPT
        available = [getattr(m, "name", "?") for m in all_models[:5]]
        raise RuntimeError(
            f"No Gemini model supports generateContent. Possible causes:\n"
            f"- API key for Vertex AI (this SDK needs AI Studio key from aistudio.google.com)\n"
            f"- Deprecated/restricted API key\n"
            f"Available models (sample): {available}"
        )

    # Prefer gemini-2.0-flash, gemini-1.5-flash if in list
    preferred = [m for m in supported if "gemini-2.0-flash" in m or "gemini-1.5-flash" in m]
    ordered = preferred if preferred else supported

    global MODELS
    if not MODELS:
        MODELS.extend(ordered)

    logger.info(f"Gemini models available: {ordered}")
    return ordered


def check_gemini_quota() -> bool:
    """Ping Gemini with minimal request. Returns True if OK, False if quota/429."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return False
    client = genai.Client(api_key=api_key)
    models_to_try = MODELS if MODELS else list_models()
    for model_name in models_to_try[:1]:  # Just try first model
        try:
            response = client.models.generate_content(
                model=model_name,
                contents="Hi",
            )
            return bool(getattr(response, "text", None))
        except Exception as e:
            if _is_quota_error(e):
                return False
            return True  # Other error - assume OK for now
    return False


class GeminiWeb:
    """Gemini with Google Search grounding (AI Studio)."""

    def __init__(self):
        global MODELS
        if not MODELS:
            MODELS.extend(list_models())

    def _get_client(self):
        return genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    async def generate_fast(self, prompt: str) -> str | None:
        """
        Gemini Fast: plain generate_content, no web. For P1 general questions.
        Returns None or GEMINI_UNAVAILABLE_QUOTA on quota error (for fallback).
        """
        models_to_try = MODELS if MODELS else list_models()
        if not models_to_try:
            return GEMINI_UNAVAILABLE_QUOTA
        client = self._get_client()

        for model_name in models_to_try:
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=prompt,
                )
                return getattr(response, "text", None) or str(response)
            except Exception as e:
                if _is_quota_error(e):
                    logger.warning(f"Gemini quota exhausted (fast): {e}")
                    return GEMINI_UNAVAILABLE_QUOTA
                logger.warning(f"Gemini {model_name} generate_fast failed: {e}")
                continue

        return GEMINI_UNAVAILABLE_QUOTA

    async def search(self, query: str) -> dict:
        """Search with Gemini + Google Search. Falls back to plain generateContent if grounding unavailable."""
        is_hebrew = any("\u0590" <= c <= "\u05FF" for c in query)

        if is_hebrew:
            prompt = f"חפש בגוגל ותן תשובה מדויקת:\n{query}\nתן עובדות + מקורות"
        else:
            prompt = f"Search Google and give accurate answer:\n{query}\nProvide facts + sources"

        models_to_try = MODELS if MODELS else list_models()
        client = self._get_client()

        # Try with Google Search grounding first
        try:
            grounding_tool = types.Tool(google_search=types.GoogleSearch())
            config_with_grounding = types.GenerateContentConfig(tools=[grounding_tool])
        except (AttributeError, TypeError) as e:
            logger.warning(f"Google Search tool not available in SDK: {e}")
            grounding_tool = None
            config_with_grounding = None

        for model_name in models_to_try:
            try:
                if config_with_grounding:
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=model_name,
                        contents=prompt,
                        config=config_with_grounding,
                    )
                else:
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=model_name,
                        contents=prompt,
                    )

                text = getattr(response, "text", None) or str(response)

                # Extract grounding metadata
                sources = []
                unique_domains = set()

                candidates = getattr(response, "candidates", []) or []
                if candidates:
                    candidate = candidates[0]
                    grounding = getattr(candidate, "grounding_metadata", None)
                    if grounding:
                        chunks = getattr(grounding, "grounding_chunks", []) or []
                        for chunk in chunks:
                            web = getattr(chunk, "web", None)
                            if web:
                                uri = getattr(web, "uri", None)
                                if uri:
                                    sources.append(chunk)
                                    try:
                                        domain = uri.split("/")[2]
                                        unique_domains.add(domain)
                                    except IndexError:
                                        pass

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
                # Quota guard: don't crash, return special object for fallback
                if _is_quota_error(e):
                    logger.warning(f"Gemini quota exhausted: {e}")
                    return {
                        "content": GEMINI_UNAVAILABLE_QUOTA,
                        "timestamp": get_timestamp(),
                        "confidence": "uncertain",
                        "sources_count": 0,
                        "unique_domains": 0,
                    }
                # If grounding failed, try without - return content with uncertainty
                err_str = str(e).lower()
                if "404" in err_str or "not found" in err_str or "not supported" in err_str:
                    logger.warning(f"Gemini {model_name} failed: {e}")
                    continue
                try:
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=model_name,
                        contents=prompt,
                    )
                    text = getattr(response, "text", None) or str(response)
                    return {
                        "content": text,
                        "timestamp": get_timestamp(),
                        "confidence": "uncertain",
                        "sources_count": 0,
                        "unique_domains": 0,
                    }
                except Exception as e2:
                    if _is_quota_error(e2):
                        logger.warning(f"Gemini quota exhausted: {e2}")
                        return {
                            "content": GEMINI_UNAVAILABLE_QUOTA,
                            "timestamp": get_timestamp(),
                            "confidence": "uncertain",
                            "sources_count": 0,
                            "unique_domains": 0,
                        }
                    logger.warning(f"Gemini {model_name} search failed: {e2}")
                    continue

        # Don't crash - return quota object for GPT fallback
        logger.error("All Gemini models failed for search")
        return {
            "content": GEMINI_UNAVAILABLE_QUOTA,
            "timestamp": get_timestamp(),
            "confidence": "uncertain",
            "sources_count": 0,
            "unique_domains": 0,
        }
