"""Priority scoring for breaking alerts (trading + AI business focus)."""

import json

from experts.gemini_client import generate_web

MIN_PRIORITY_SCORE = 70


def _extract_json_object(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        data = json.loads(raw[start : end + 1])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class PriorityAgent:
    async def score_event(self, verified: dict) -> dict:
        """
        Input: verified event (after verification)
        Output: dict with should_send, priority_score (0-100), reason
        """
        payload = json.dumps(verified, ensure_ascii=False, indent=2)
        prompt = (
            "אתה מנוע עדיפות להתראות שוק ו-AI. המשתמש מתמקד במסחר ובעסקי AI (לא רעש כללי).\n"
            "קיבלת אירוע שכבר עבר שכבת אימות טכנית. הערך רק ערך אמיתי למשתמש.\n"
            "\n"
            "האירוע:\n"
            f"{payload}\n"
            "\n"
            "הערך לפי:\n"
            "- השפעת שוק: מדדים, תשואות, נפט, מאקרו, תנועות מהותיות (לא כותרת ריקה)\n"
            "- השפעת AI: OpenAI, Nvidia, Google, תשתית, רגולציה, עסקים מהותיים\n"
            "- מיידיות: האם משפיע עכשיו או רק רעש/חזרה על ידיעה ישנה\n"
            "\n"
            "כללים קשיחים:\n"
            "- העדף שינויי מאקרו/מגמה על פני כותרות ריקות\n"
            "- דחה כפילויות, רעש, ספקולציה ללא השפעה ממשית\n"
            "- החזר JSON בלבד:\n"
            "{\n"
            '  "should_send": true/false,\n'
            '  "priority_score": 0-100,\n'
            '  "reason": "הסבר קצר בעברית"\n'
            "}\n"
            f"- שלח רק אם priority_score >= {MIN_PRIORITY_SCORE}; אחרת should_send=false.\n"
        )
        raw = await generate_web(prompt)
        out = _extract_json_object(raw)
        score = int(out.get("priority_score") or 0)
        should = bool(out.get("should_send")) and score >= MIN_PRIORITY_SCORE
        reason = (out.get("reason") or "").strip() or "—"
        return {
            "should_send": should,
            "priority_score": min(100, max(0, score)),
            "reason": reason,
        }
