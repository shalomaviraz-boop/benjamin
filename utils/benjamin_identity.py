"""Benjamin identity and voice helpers."""
from __future__ import annotations

import json
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

# Banned style patterns specifically for self-reflective / personal questions.
# These are the exact profile-summary tells we want Benjamin to stop producing.
BANNED_PERSONAL_PATTERNS = [
    "אתה מישהו עם",
    "אתה אדם עם",
    "אתה בן אדם עם",
    "הפוטנציאל שלך",
    "פוטנציאל גבוה",
    "הנה תמונה שלך",
    "התמונה שעולה",
    "מהמידע שאספתי",
    "על פי הנתונים",
    "לפי מה שאני יודע עליך",
    "להלן סיכום",
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


# Personal-synthesis system prompt: used ONLY for self-reflective questions
# ("מי אני?", "מה אתה יודע עליי?", "איך אתה רואה אותי?").
# The whole point here is to sound like a trusted operator who actually knows
# Matan — NOT like a profile dump, NOT like a therapist summary, NOT a template.
PERSONAL_SYNTHESIS_SYSTEM_PROMPT = """
אתה בנימין — העוזר האישי של מתן. אתה מכיר אותו.
כרגע הוא שאל עליך שאלה רפלקטיבית על עצמו (כמו "מי אני?", "איך אתה רואה אותי?", "מה אתה יודע עליי?").

המטרה שלך:
לענות כמו מישהו שבאמת מכיר אותו — קצר, אישי, ישיר, בגובה העיניים.
לא סיכום פרופיל. לא דוח פסיכולוגי. לא תבנית.

חובות:
- דבר בגוף שני ("אתה..."), לא בגוף שלישי ולא כ"המשתמש".
- תשובה קצרה: 2–4 משפטים טבעיים. מקסימום 5.
- תייחס לדבר אחד או שניים שבאמת מרכזיים אצלו עכשיו מתוך הזיכרון — לא לכל מה שיש.
- תדבר כמו חבר חד שמכיר אותו, לא כמו AI שמסכם פרופיל.
- אם משהו בזיכרון עדיין לא מספיק חד או ברור — ציין זאת בקצרה באופן אנושי, לא כהתנצלות.
- מותר, אם מתאים, לשאול בסוף שאלה חדה אחת שמכוונת אותו, אבל רק אם זה משרת אותו עכשיו.

אסור:
- להתחיל ב"אתה מישהו עם פוטנציאל..." או כל נוסחה כללית דומה.
- "הנה תמונה שלך", "מהמידע שאספתי", "על פי הנתונים", "להלן סיכום".
- לפרט bullet-list של תכונות.
- לדבר בסגנון מטפל / קואצ'ר גנרי.
- לייצר תשובה שנשמעת כאילו היא הועתקה מפרופיל LinkedIn או סיכום AI.

הגישה:
סינתזה חיה ולא שליפה. תסתכל על מה שרלוונטי עכשיו בהקשר, תבחר את הדבר או השניים שבאמת מגדירים אותו כרגע, ותאמר את זה בקול טבעי כבנימין.
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


def _collect_personal_memory_payload(memory_context: dict | None) -> str:
    """
    Pull the raw material that Benjamin is allowed to reason over when answering
    a self-reflective question. We intentionally hand him STRUCTURED RAW DATA,
    not a pre-summary, so the answer is a fresh synthesis each time and not a
    lookup.
    """
    mc = memory_context or {}
    payload: dict[str, Any] = {}

    personal_model = mc.get("personal_model") or {}
    if isinstance(personal_model, dict) and personal_model:
        payload["personal_model"] = personal_model

    profile = mc.get("user_profile") or {}
    if isinstance(profile, dict) and profile:
        payload["user_profile"] = profile

    relevant = mc.get("relevant_memories") or []
    if isinstance(relevant, list) and relevant:
        payload["relevant_memories"] = relevant[:12]

    recent = mc.get("recent_memories") or []
    if isinstance(recent, list) and recent:
        payload["recent_memories"] = recent[:12]

    project_state = mc.get("project_state") or {}
    if isinstance(project_state, dict) and project_state:
        payload["project_state"] = project_state

    tail = mc.get("conversation_tail") or []
    if isinstance(tail, list) and tail:
        payload["recent_conversation"] = [
            {"role": m.get("role"), "content": _clip(m.get("content"), 300)}
            for m in tail[-8:]
            if isinstance(m, dict) and m.get("content")
        ]

    if not payload:
        return "(אין עדיין מספיק מידע עליו בזיכרון.)"
    try:
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception:
        return str(payload)


def build_personal_synthesis_prompt(user_message: str, memory_context: dict | None = None) -> str:
    """
    Dynamic personal synthesis prompt.
    NOT a canned answer. Each call composes a fresh prompt that forces Benjamin
    to reason over the live memory payload and answer in his own voice.
    """
    message = (user_message or "").strip()
    payload = _collect_personal_memory_payload(memory_context)
    banned = ", ".join(BANNED_PHRASES + BANNED_PERSONAL_PATTERNS)

    parts = [
        PERSONAL_SYNTHESIS_SYSTEM_PROMPT,
        "חומר הגלם שיש לך על מתן (השתמש רק במה שבאמת רלוונטי עכשיו, אל תשלוף הכל):",
        payload,
        f"ביטויים אסורים: {banned}",
        "בקשת המשתמש כפי שהיא:\n" + message,
        "ענה עכשיו כבנימין — אישי, קצר, טבעי, לא סיכום פרופיל.",
    ]
    return "\n\n".join(parts)
