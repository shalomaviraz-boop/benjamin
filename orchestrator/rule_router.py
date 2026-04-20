import re


# Self-reflective / identity questions ("who am I", "what do you know about me", etc).
# Matched as whole-phrase / tight substrings to avoid false positives.
_PERSONAL_SYNTHESIS_PATTERNS = [
    r"\bמי אני\b",
    r"\bמי אני\?",
    r"מה אתה יודע עלי[יי]?",
    r"מה את יודעת עלי[יי]?",
    r"איך אתה רואה אותי",
    r"איך את רואה אותי",
    r"מה דעתך עלי[יי]?",
    r"מה אתה חושב עלי[יי]?",
    r"איך אתה מגדיר אותי",
    r"תאר אותי",
    r"מה אתה מבין עלי[יי]?",
    r"who am i\b",
    r"what do you (?:know|think) about me\b",
    r"how do you see me\b",
]

_PERSONAL_SYNTHESIS_REGEX = re.compile("|".join(_PERSONAL_SYNTHESIS_PATTERNS), re.IGNORECASE)


# Latest-news / realtime keywords. If any of these appears, we MUST route through web.
# This is intentionally aggressive because stale cutoff answers are the failure mode
# we are trying to eliminate.
_NEWS_KEYWORDS = [
    "חדשות אחרונות",
    "החדשות האחרונות",
    "חדשות",
    "עדכונים אחרונים",
    "עדכון אחרון",
    "עדכונים",
    "מה חדש אצל",
    "מה חדש ב",
    "מה חדש עם",
    "מה חדש",
    "מה קורה עם",
    "מה קורה ב",
    "מה קורה אצל",
    "מה קרה היום",
    "מה קרה אתמול",
    "היום בחדשות",
    "פריצות דרך",
    "הכרזות אחרונות",
    "release",
    "releases",
    "launch",
    "latest news",
    "latest update",
    "latest updates",
    "recent news",
    "breaking news",
    "news",
    "breaking",
    "market scan",
    "news scan",
    "today in",
    "this week",
    "this morning",
]


def _contains_news_keyword(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in _NEWS_KEYWORDS)


class RuleRouter:
    def route(self, message: str) -> dict | None:
        raw = (message or "").strip()
        text = raw.lower()

        # Self-reflective / identity question → personal_synthesis.
        # Checked FIRST so that "מי אני" is not stolen by other keyword rules.
        if raw and _PERSONAL_SYNTHESIS_REGEX.search(raw):
            return {
                "task_type": "personal_synthesis",
                "routing_source": "rule",
                "execution_mode": "direct",
                "use_web": False,
                "require_verification": False,
                "require_code_review": False,
                "reason": "self-reflective question → dynamic personal synthesis",
            }

        # Latest-news / realtime query → MUST go through web.
        # grounded_web=True tells the orchestrator NOT to re-run Claude sanity-check
        # on the answer (Claude has no web access and would overwrite it with
        # stale cutoff knowledge).
        if _contains_news_keyword(text):
            return {
                "task_type": "research",
                "routing_source": "rule",
                "execution_mode": "direct",
                "use_web": True,
                "grounded_web": True,
                "require_verification": False,
                "reason": "news/latest/update query → forced realtime web path",
            }

        if any(x in text for x in ["תזכור", "תשמור", "שכח", "תמחק זיכרון", "remember", "forget"]):
            return {
                "task_type": "memory",
                "routing_source": "rule",
                "execution_mode": "direct",
                "reason": "memory request matched rule router",
            }

        if any(x in text for x in ["אימון", "כושר", "תזונה", "מסה", "חיטוב", "קלור", "חלבון", "ארוחה", "diet", "nutrition", "workout", "bulk", "cut"]):
            return {
                "task_type": "fitness_health",
                "routing_source": "rule",
                "execution_mode": "direct",
                "reason": "fitness/health request matched rule router",
            }

        if any(x in text for x in ["קוד", "תכתוב", "תבנה פונקציה", "python", "bug", "error", "stack trace", "exception", "refactor", "architecture"]):
            return {
                "task_type": "code",
                "routing_source": "rule",
                "execution_mode": "direct",
                "require_code_review": True,
                "reason": "code request matched rule router",
            }

        if any(x in text for x in ["מניה", "מניות", "מדד", "שוק", "מאקרו", "finance", "stock", "stocks", "macro", "ta35", "spx", "qqq", "spy"]):
            return {
                "task_type": "finance",
                "routing_source": "rule",
                "execution_mode": "direct",
                "use_web": True,
                "grounded_web": True,
                "require_verification": False,
                "reason": "finance request matched rule router",
            }

        if any(x in text for x in ["תזכיר", "יומן", "לו""ז", "משימה", "תארגן", "calendar", "schedule", "reminder", "assistant"]):
            return {
                "task_type": "assistant",
                "routing_source": "rule",
                "execution_mode": "direct",
                "reason": "assistant request matched rule router",
            }

        if any(x in text for x in ["זוגיות", "אקסית", "קשר", "בחורה", "דייט", "רגשות", "תקשורת", "relationship", "dating", "ex", "social"]):
            return {
                "task_type": "relationships",
                "routing_source": "rule",
                "execution_mode": "direct",
                "reason": "relationship request matched rule router",
            }

        if any(x in text for x in ["עסק", "אסטרטגיה", "הצעה", "מוצר", "לקוחות", "מכירות", "מוניטיזציה", "growth", "pricing", "gtm", "business", "offer", "strategy"]):
            return {
                "task_type": "business_strategy",
                "routing_source": "rule",
                "execution_mode": "direct",
                "reason": "business strategy request matched rule router",
            }

        # AI-company / model questions. If the phrasing also contains a news keyword
        # it is already captured by the news branch above, so what reaches here is
        # generic AI discussion. Still route through web because AI moves fast.
        if any(x in text for x in ["ai", "artificial intelligence", "machine learning", "llm", "gpt", "claude", "gemini", "anthropic", "openai", "מודל", "מודלים", "בינה מלאכותית", "למידת מכונה", "אייגנט", "אייגנטים"]):
            return {
                "task_type": "ai_expert",
                "routing_source": "rule",
                "execution_mode": "direct",
                "use_web": True,
                "grounded_web": True,
                "require_verification": False,
                "reason": "ai expert request matched rule router",
            }

        if any(x in text for x in ["עצור", "בטל", "אשר", "תאשר", "approve", "cancel", "stop"]):
            return {
                "task_type": "execution",
                "routing_source": "rule",
                "execution_mode": "direct",
                "reason": "control request matched rule router",
            }

        return None
