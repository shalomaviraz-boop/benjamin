"""Final pass over user-facing text: strip ban phrases, source dumps, robotic intros."""

from __future__ import annotations

import re

BANNED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^\s*להלן\s+(?:גרסה|הצעה|סיכום|תקציר|רשימה|הפירוט)[^\n.:]*[:.]?\s*", re.MULTILINE), ""),
    (re.compile(r"^\s*הנה\s+(?:גרסה|הצעה|תקציר|סיכום|רשימה|הפירוט)[^\n.:]*[:.]?\s*", re.MULTILINE), ""),
    (re.compile(r"^\s*לסיכום[^\n]*[:.]?\s*", re.MULTILINE), ""),
    (re.compile(r"^\s*נכון\s+ל[^,\n.]+[,.\s]*", re.MULTILINE), ""),
    (re.compile(r"^\s*intelligence\s+report[^\n]*", re.IGNORECASE | re.MULTILINE), ""),
    (re.compile(r"^\s*daily\s+intelligence[^\n]*", re.IGNORECASE | re.MULTILINE), ""),
    (re.compile(r"^\s*איך\s+זה\s+מתקשר\s+ל[^\n?]*\??\s*", re.MULTILINE), ""),
    (re.compile(r"^\s*מה\s+אתה\s+מנסה\s+להשיג[^\n?]*\??\s*", re.MULTILINE), ""),
]

URL_PATTERN = re.compile(r"https?://\S+")
SOURCE_BLOCK_PATTERNS = [
    re.compile(r"^\s*(?:sources?|מקורות|קישורים|references?)\s*[:\-]\s*$.*", re.IGNORECASE | re.MULTILINE | re.DOTALL),
    re.compile(r"^\s*\[\d+\]\s+https?://\S+.*$", re.MULTILINE),
]
INLINE_NUMERIC_CITATION = re.compile(r"\s*\[\s*\d+(?:\s*,\s*\d+)*\s*\]")


def strip_source_dumps(text: str) -> str:
    if not text:
        return text
    cleaned = text
    for pattern in SOURCE_BLOCK_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    cleaned = INLINE_NUMERIC_CITATION.sub("", cleaned)
    lines = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append(line)
            continue
        if stripped.lower().startswith(("source:", "sources:", "מקור:", "מקורות:", "ref:", "references:")):
            continue
        url_only = URL_PATTERN.sub("", stripped).strip(" -•*[]()")
        if not url_only:
            continue
        sanitized_line = URL_PATTERN.sub("", line)
        sanitized_line = re.sub(r"[ \t]{2,}", " ", sanitized_line).rstrip(" -•*[]()\t")
        lines.append(sanitized_line)
    return "\n".join(lines).strip()


def strip_banned_phrases(text: str) -> str:
    if not text:
        return text
    cleaned = text
    for pattern, replacement in BANNED_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


def collapse_blank_lines(text: str) -> str:
    if not text:
        return text
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def sanitize_user_facing_text(text: str) -> str:
    """Run all final-pass scrubs. Safe to call on already-clean text."""
    if not text:
        return text
    cleaned = strip_banned_phrases(text)
    cleaned = strip_source_dumps(cleaned)
    cleaned = collapse_blank_lines(cleaned)
    return cleaned


def looks_robotic(text: str) -> bool:
    """Heuristic: opens with one of the banned framings."""
    if not text:
        return False
    head = text.strip().splitlines()[0][:60].lower() if text.strip() else ""
    triggers = ("להלן", "לסיכום", "נכון ל", "intelligence report", "daily intelligence")
    return any(head.startswith(t) for t in triggers)
