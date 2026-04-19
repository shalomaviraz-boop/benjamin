"""Priority scoring for breaking alerts (trading + AI business focus)."""

import json

from experts.model_router import model_router

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
    async def score_event(self, verified: dict, memory_context: dict | None = None) -> dict:
        """
        Input: verified event (after verification)
        Output: dict with should_send, priority_score (0-100), reason
        """
        payload = json.dumps(verified, ensure_ascii=False, indent=2)
        prompt = (
            "אתה מנוע עדיפות אישי להתראות של בנימין.\n"
            "קיבלת אירוע שכבר עבר שכבת אימות טכנית. תחליט אם שווה להפריע למשתמש עכשיו.\n"
            "\n"
            "האירוע:\n"
            f"{payload}\n"
            "\n"
            "תעדף לפי:\n"
            "- רלוונטיות ישירה ל-Super Agent / premium personal AI assistant\n"
            "- מהלך AI חשוב באמת: OpenAI / Anthropic / Google / Meta / xAI / infra / tooling / pricing / reliability\n"
            "- הזדמנות עסקית או אסטרטגית שהמשתמש יכול לנצל\n"
            "- שוק/מאקרו רק אם זה באמת חשוב לתחומי העניין שלו\n"
            "- מיידיות: האם זה משנה משהו עכשיו או שזה רעש\n"
            "\n"
            "כללים קשיחים:\n"
            "- דחה חדשות עולם גנריות, filler, headlines בלי leverage, או דברים שלא יזיזו למשתמש.\n"
            "- דחה כפילויות, רעש, ספקולציה ללא השפעה ממשית.\n"
            "- שלח רק אם זה גם חשוב וגם אישי.\n"
            "- החזר JSON בלבד:\n"
            "{\n"
            '  "should_send": true/false,\n'
            '  "priority_score": 0-100,\n'
            '  "user_relevance_score": 0-100,\n'
            '  "opportunity": "משפט קצר בעברית עם ה-leverage או ה-next move, או ריק",\n'
            '  "reason": "הסבר קצר בעברית"\n'
            "}\n"
            f"- שלח רק אם priority_score >= {MIN_PRIORITY_SCORE}; אחרת should_send=false.\n"
        )
        raw, _ = await model_router.generate(
            prompt=prompt,
            task_type="assistant",
            memory_context=memory_context,
            use_web=False,
        )
        out = _extract_json_object(raw)
        score = int(out.get("priority_score") or 0)
        relevance = int(out.get("user_relevance_score") or 0)
        should = bool(out.get("should_send")) and score >= MIN_PRIORITY_SCORE and relevance >= 75
        reason = (out.get("reason") or "").strip() or "—"
        opportunity = (out.get("opportunity") or "").strip()
        return {
            "should_send": should,
            "priority_score": min(100, max(0, score)),
            "user_relevance_score": min(100, max(0, relevance)),
            "opportunity": opportunity,
            "reason": reason,
        }
