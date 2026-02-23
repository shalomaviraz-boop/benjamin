"""Helper utilities for Benjamin."""
from datetime import datetime
from pytz import timezone
import re

TIMEZONE = timezone("Asia/Jerusalem")


def get_timestamp() -> str:
    """Get timestamp in IST format."""
    now = datetime.now(TIMEZONE)
    return now.strftime("%d/%m/%Y, %H:%M (IST)")


def extract_issues(sanity_text: str) -> list[str]:
    """Extract issues list from sanity check."""
    if "ISSUES: None" in sanity_text or "ISSUES: none" in sanity_text.lower():
        return []

    if "ISSUES:" in sanity_text:
        issues_section = sanity_text.split("ISSUES:")[1].strip()
        issues = [
            line.strip("- ").strip()
            for line in issues_section.split("\n")
            if line.strip() and not line.startswith("VERDICT")
        ]
        return issues[:3]

    return []


def is_high_risk(message: str) -> bool:
    """Check if message is high-risk (2 layers)."""
    msg_lower = message.lower()

    # Layer 1: Keywords
    HIGH_RISK_KEYWORDS = [
        "כסף", "מסחר", "השקעה", "קנה", "מכור", "trade", "invest",
        "תרופה", "רופא", "בריאות", "מחלה", "טיפול", "health", "medical",
        "חוק", "משפט", "חוזה", "זכויות", "legal", "contract",
        "ביטול", "תשלום", "העברה", "מחיקה", "delete", "cancel", "transfer",
    ]

    if any(kw in msg_lower for kw in HIGH_RISK_KEYWORDS):
        return True

    # Layer 2: Logic patterns
    # Pattern 1: Action instructions
    action_patterns = ["תן לי הוראות", "איך לבצע", "give me instructions", "how to execute"]
    action_verbs = ["transfer", "cancel", "pay", "העבר", "בטל", "שלם"]

    has_action = any(p in msg_lower for p in action_patterns)
    has_verb = any(v in msg_lower for v in action_verbs)

    if has_action and has_verb:
        return True

    # Pattern 2: Financial numbers
    financial_regex = [r"\d+\s*[$₪€£¥]", r"[$₪€£¥]\s*\d+", r"\d+\s*%", r"\d+x"]
    trading_terms = ["מינוף", "leverage", "אופציות", "options"]

    has_numbers = any(re.search(p, msg_lower) for p in financial_regex)
    has_trading = any(t in msg_lower for t in trading_terms)

    if has_numbers and has_trading:
        return True

    return False
