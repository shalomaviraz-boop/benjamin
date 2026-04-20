"""Benjamin identity and voice helpers."""
from __future__ import annotations

from typing import Any

BANNED_PHRASES = [
    "להלן",
    "לסיכום",
    "נכון ל",
    "הנה גרסה מקצועית",
    "הנה הצעה לניסוח",
    "intelligence report",
    "daily intelligence",
    "איך זה מתקשר למטרות שלך",
    "מה אתה מנסה להשיג בשאלה הזו",
]

BENJAMIN_SYSTEM_PROMPT = """
אתה בנימין.
אתה לא בוט חדשות, לא יועץ גנרי ולא מודל שפה שמסביר איך הוא חושב.
אתה עוזר אישי פרימיום של מתן.

איך אתה מדבר:
- קצר, חד, ברור וטבעי
- כמו מישהו שמכיר את מתן וחושב איתו בגובה העיניים
- בלי הקדמות מיותרות
- בלי ניסוחים רובוטיים
- בלי 'להלן', 'לסיכום', 'נכון ל', 'הנה גרסה מקצועית'
- בלי לשאול שאלת המשך חלשה כשכבר יש מספיק הקשר לענות
- אם יש עובדה לא ודאית: אומרים בקצרה שלא בטוחים, לא ממציאים
- אם צריך לבחור כיוון: ממליצים חד

איך אתה עוזר:
- קודם מבין מה מתן באמת צריך עכשיו
- משתמש בהקשר ובזיכרון רק אם הוא באמת רלוונטי
- מחזיר מינימום מילים עם מקסימום ערך
- כשיש הקשר אישי ברור, עונים אישית ולא גנרית
- כשזו שאלה על חדשות/שוק/AI: תן עובדות עדכניות, בלי הייפ ובלי דרמה
""".strip()


def _clip(value: Any, n: int = 240) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n].rstrip() + "…"


def build_user_brief(memory_context: dict | None) -> str:
    mc = memory_context or {}
    model = mc.get("personal_model") or {}
    if not isinstance(model, dict):
        return ""

    chunks: list[str] = []

    if model.get("name"):
        chunks.append(f"שם: {_clip(model.get('name'), 40)}")

    stable = model.get("identity_core") or model.get("identity")
    if stable:
        chunks.append(f"זהות: {_clip(stable, 180)}")

    if model.get("communication_style"):
        chunks.append(f"סגנון מועדף: {_clip(model.get('communication_style'), 160)}")

    mission = model.get("current_main_mission") or model.get("main_mission")
    if mission:
        chunks.append(f"מטרה מרכזית: {_clip(mission, 140)}")

    active_goals = model.get("active_goals")
    if isinstance(active_goals, list) and active_goals:
        chunks.append("יעדים פעילים: " + ", ".join(_clip(x, 50) for x in active_goals[:5]))

    fitness = model.get("fitness_goal")
    if isinstance(fitness, dict) and fitness:
        parts = []
        if fitness.get("goal_type"):
            parts.append(str(fitness["goal_type"]))
        if fitness.get("current_weight"):
            parts.append(f"נוכחי {fitness['current_weight']}")
        if fitness.get("target_weight"):
            parts.append(f"יעד {fitness['target_weight']}")
        if parts:
            chunks.append("כושר: " + ", ".join(parts))

    if model.get("relationship_patterns"):
        chunks.append(f"דפוסי זוגיות: {_clip(model.get('relationship_patterns'), 180)}")

    return "\n".join(chunks)


def build_benjamin_user_prompt(user_message: str, memory_context: dict | None = None) -> str:
    message = (user_message or "").strip()
    brief = build_user_brief(memory_context)
    banned = ", ".join(BANNED_PHRASES)
    parts = [BENJAMIN_SYSTEM_PROMPT]
    if brief:
        parts.append("הקשר רלוונטי על מתן:\n" + brief)
    parts.append(f"ביטויים אסורים: {banned}")
    parts.append("בקשת המשתמש:\n" + message)
    parts.append("ענה עכשיו כבנימין בלבד.")
    return "\n\n".join(parts)
