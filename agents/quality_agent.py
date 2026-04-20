"""Cleanup outbound proactive text without robotic rewrite wrappers."""
from __future__ import annotations

import re


class QualityAgent:
    async def polish(self, text: str) -> str:
        cleaned = (text or "").strip()
        cleaned = re.sub(r"^להלן[^\n]*\n+", "", cleaned)
        cleaned = re.sub(r"^הנה הצעה לנוסח[^\n]*\n+", "", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()
