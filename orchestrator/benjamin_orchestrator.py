"""Benjamin Orchestrator - Rule-based routing and pipeline execution."""
import re

from pipelines import p1_direct
from pipelines import p2_web_grounded
from pipelines import p3_reasoning
from pipelines import p4_code
from utils.logger import logger, log_pipeline


# === P4: Code keywords (priority 1) ===
P4_CODE_PATTERNS = [
    r"\b(כתוב|כתובי|כתב)\s*(קוד|פונקציה|מחלקה|סקריפט|script)",
    r"\b(פונקציה|function|def|class|מחלקה)\s",
    r"\b(דיבוג|debug|שיפור)\s*(קוד|הקוד)?",
    r"\b(קוד|code)\s*(ל|לעבוד|שעובד|שיעבוד)",
    r"\bsnippet\b",
    r"\b(איך|how)\s+to\s+(write|code|implement)",
    r"\b(ממש|implement)\s*(פונקציה|מחלקה)",
    r"\b(בנה|build)\s*(פונקציה|מחלקה|סקריפט)",
    r"\b(פתור|solve)\s*(ב|with)\s*(קוד|code)",
    r"\b(תרגם|translate)\s*(ל|to)\s*(פייתון|python|java)",
]

# === P3: Reasoning/analysis keywords (priority 2) ===
P3_REASONING_PATTERNS = [
    r"\b(ניתוח|analysis|analyze)\b",
    r"\b(השוואה|compare|comparison)\b",
    r"\b(תכנון|planning|plan)\b",
    r"\b(אסטרטגיה|strategy)\b",
    r"\b(החלטה|decision)\b",
    r"\b(trade-off|tradeoff|trade off)\b",
    r"\b(איך לבחור|which to choose|what to choose)\b",
    r"\b(מה עדיף|מה יותר|which is better)\b",
    r"\b(יתרונות וחסרונות|pros and cons)\b",
    r"\b(שיקולי|considerations)\b",
    r"\b(המלצה|recommendation)\b",
    r"\b(השוואת|השוואתי)\b",
]

# === P2: Factual question indicators (default for facts) ===
P2_FACTUAL_PATTERNS = [
    r"\b(מי|who)\b",
    r"\b(מתי|when)\b",
    r"\b(כמה|how much|how many)\b",
    r"\b(איפה|where)\b",
    r"\b(מה (ה)?מחיר|מה השער|price|rate)\b",
    r"\b(מה (ה)?גרסה|version|latest)\b",
    r"\b(מה (ה)?תוצאה|result|winner)\b",
    r"\b(היום|עכשיו|אתמול|השנה|השבוע)\b",
    r"\b(current|latest|now|today|yesterday)\b",
    r"\b(מזג אוויר|weather)\b",
    r"\b(שער|rate|exchange)\s*(דולר|שקל|יורו)\b",
    r"\b(נשיא|ראש ממשלה|president)\b",
    r"\b(זכה|won|winner)\b",
]

# === P1 exception: time/version/currency - DISQUALIFIES p1 ===
P1_DISQUALIFY_PATTERNS = [
    r"\b(היום|עכשיו|אתמול|השנה|השבוע|מחר)\b",
    r"\b(current|latest|version|now|today)\b",
    r"\b(מחיר|שער|גרסה|מנוי|subscription)\b",
    r"\b(\$|₪|€|£)\s*\d|\d+\s*(\$|₪|€|£)\b",
]

# === P1: Static fact patterns (science, math, history) ===
P1_STATIC_PATTERNS = [
    r"\b(נוסחה|formula)\s*(של|of)\b",
    r"\b(כמה .* יש ב|how many .* in)\b",  # כמה שניות בדקה
    r"\b(באיזו שנה|in what year|when did)\b",
    r"\b(מה ההגדרה|definition of)\b",
    r"\b(הסבר|explain)\s*(מה|what is|me)?\b",
    r"\b(מה זה|what is)\s+\w+\b",  # מה זה machine learning
]


def _decide_pipeline(message: str, context: str = "") -> dict[str, str]:
    """
    Rule-based pipeline selection. Deterministic.
    Priority: p4 → p3 → p2 (factual) → p1 (exception only).
    Golden rule: when in doubt → p2.
    """
    msg_lower = message.strip().lower()

    # 1. Code request → always p4
    for pattern in P4_CODE_PATTERNS:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            return {"pipeline": "p4", "reasoning": "בקשת קוד/פונקציה/דיבוג"}

    # 2. Complex analysis/comparison/planning → p3
    for pattern in P3_REASONING_PATTERNS:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            return {"pipeline": "p3", "reasoning": "ניתוח/השוואה/תכנון מורכב"}

    # 3. Factual question → default p2
    is_factual = any(re.search(p, msg_lower, re.IGNORECASE) for p in P2_FACTUAL_PATTERNS)

    # 4. P1 exception: only if static fact AND no disqualifiers
    if is_factual:
        # Check if p1 exception (static fact, no time/version/price)
        has_disqualifier = any(
            re.search(p, msg_lower, re.IGNORECASE) for p in P1_DISQUALIFY_PATTERNS
        )
        has_static_pattern = any(
            re.search(p, msg_lower, re.IGNORECASE) for p in P1_STATIC_PATTERNS
        )

        if has_static_pattern and not has_disqualifier:
            return {"pipeline": "p1", "reasoning": "עובדה סטטית מדעית/מתמטית/היסטורית"}

        # Factual but not p1 exception → p2
        return {"pipeline": "p2", "reasoning": "שאלה עובדתית"}

    # 5. Not clearly factual - could be general explanation
    # Check for p1-style (general question, no time/version)
    has_disqualifier = any(
        re.search(p, msg_lower, re.IGNORECASE) for p in P1_DISQUALIFY_PATTERNS
    )
    has_static_pattern = any(
        re.search(p, msg_lower, re.IGNORECASE) for p in P1_STATIC_PATTERNS
    )

    if has_static_pattern and not has_disqualifier:
        return {"pipeline": "p1", "reasoning": "שאלת הסבר סטטית"}

    # 6. Golden rule: when in doubt → p2
    return {"pipeline": "p2", "reasoning": "ספק - ברירת מחדל p2"}


class BenjaminOrchestrator:
    """Orchestrates rule-based routing and pipeline execution."""

    def __init__(self):
        pass

    async def route_and_execute(self, message: str, context: str = "") -> str:
        """Decide pipeline and execute."""
        decision = _decide_pipeline(message, context)
        pipeline = decision["pipeline"]
        reasoning = decision["reasoning"]

        logger.info(f"Routing: {pipeline} | Reasoning: {reasoning}")

        try:
            if pipeline == "p1":
                result = await p1_direct.run(message)
            elif pipeline == "p2":
                result = await p2_web_grounded.run(message)
            elif pipeline == "p3":
                result = await p3_reasoning.run(message, context)
            elif pipeline == "p4":
                result = await p4_code.run(message)
            else:
                result = await p2_web_grounded.run(message)
                pipeline = "p2"

            log_pipeline(pipeline, message, True)
            return result

        except Exception as e:
            logger.error(f"Pipeline {pipeline} failed: {e}")
            log_pipeline(pipeline, message, False)
            raise
