class RuleRouter:
    def route(self, message: str) -> dict | None:
        text = (message or "").strip().lower()

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
                "require_verification": True,
                "reason": "finance request matched rule router",
            }

        if any(x in text for x in ["חדשות", "news", "breaking", "market scan", "news scan"]):
            return {
                "task_type": "research",
                "routing_source": "rule",
                "execution_mode": "direct",
                "use_web": True,
                "require_verification": True,
                "reason": "research/news request matched rule router",
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

        if any(x in text for x in ["ai", "artificial intelligence", "machine learning", "llm", "gpt", "claude", "gemini", "anthropic", "openai", "מודל", "מודלים", "בינה מלאכותית", "למידת מכונה", "אייגנט", "אייגנטים"]):
            return {
                "task_type": "ai_expert",
                "routing_source": "rule",
                "execution_mode": "direct",
                "use_web": True,
                "require_verification": True,
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
