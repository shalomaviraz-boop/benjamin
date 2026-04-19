# memory/memory_store.py
import json
import os
import re
import sqlite3
import time
from typing import Any

DB_PATH = os.getenv("BENJAMIN_MEMORY_DB", "benjamin_memory.db")

MEMORY_TYPES = (
    "identity",
    "preference",
    "project",
    "behavioral",
    "relational",
    "temporal",
    "strategic",
)

LEGACY_TYPE_MAP = {
    "fact": "identity",
    "profile": "identity",
    "identity": "identity",
    "preference": "preference",
    "dislike": "preference",
    "project": "project",
    "goal": "strategic",
    "note": "temporal",
    "temporal": "temporal",
    "behavioral": "behavioral",
    "relational": "relational",
    "strategic": "strategic",
}

EXPANDED_CORE_PROFILE_TEXT = """DYNAMIC USER MODEL — MATAN (EXPANDED CORE PROFILE)

Identity Core:
מתן הוא אדם עם פוטנציאל גבוה שלא מומש במלואו עדיין, והוא יודע את זה. זה יוצר מתח פנימי קבוע: מצד אחד תחושת מסוגלות אמיתית, מצד שני תסכול מכך שהחיים בפועל עדיין לא משקפים את הרמה שהוא מרגיש שיש בו. הוא לא אדם בינוני שמרוצה משגרה. הוא צריך תחושת גדילה, יתרון, תנועה, בנייה. כשהחיים סטטיים מדי — הוא נשחק.

Mental Structure:
מתן חושב אסטרטגית יותר מרוב האנשים. הוא מחפש leverage, קיצורי דרך חכמים, זוויות שלא כולם רואים. הוא לא נהנה מעבודה סיזיפית חסרת משמעות. אם משהו מרגיש "קטן", איטי או טיפשי — קשה לו להתמסר אליו. לכן הוא מסוגל להיות חד מאוד מחשבתית, אבל גם להיתקע כשאין מטרה שמעוררת אותו.

Core Internal Conflict:
יש אצלו פער בין רמת המודעות לרמת הביצוע. הוא מבין דברים עמוק, מזהה דפוסים, קולט אנשים, רואה טעויות — אבל לא תמיד מתרגם זאת לעקביות יומיומית. הוא יודע מה צריך לעשות יותר פעמים ממה שהוא עושה בפועל. זה יוצר ביקורת עצמית סמויה.

Strengths:
- אינטליגנציה אינטואיטיבית גבוהה
- קליטה מהירה של מערכות ואנשים
- יכולת לראות תמונה רחבה
- כריזמה טבעית כשבמצב טוב
- חשיבה עסקית / אסטרטגית
- אומץ לחשוב בגדול
- לא מקבל אוטומטית מוסכמות חברתיות
- יכולת ליצור חיבור עם אנשים

Weaknesses:
- חוסר סבלנות לתהליכים איטיים
- קושי בהתמדה כשאין ריגוש
- נטייה לעבור בין כיוונים
- צורך בהוכחה חיצונית בתקופות מסוימות
- overthinking בהחלטות רגשיות
- רגישות לבינוניות ולחוסר חדות
- לפעמים מחפש מהלך גדול במקום רצף מהלכים קטנים

Emotional Profile:
מתן עמוק יותר ממה שהוא משדר. כלפי חוץ הוא עשוי להיראות חד, בשליטה, ציני או ענייני — אבל בפנים יש צורך אמיתי במשמעות, כבוד, חיבור, ואהבה איכותית. הוא לא נפתח לכל אחד. כשהוא כן נקשר — זה חזק.

Relationship Patterns:
- לא מתרגש מקשרים שטחיים
- מחפש חיבור נדיר, איכותי, מיוחד
- כשהוא מרגיש שמצא משהו אמיתי — נכנס חזק רגשית
- עלול להיקשר יותר לאפשרות ולפוטנציאל מאשר למציאות
- רגיש לדחייה / חוסר הדדיות
- לפעמים רוצה שליטה כשהוא מרגיש חוסר ודאות
- קשה לו לשחרר סיפורים לא סגורים

Past Relationship Impact:
הקשר האחרון השאיר חותם עמוק יותר ממה שמתן אוהב להודות. לא רק בגלל הבחורה עצמה — אלא בגלל מה שהקשר סימל: אפשרות לחיים אחרים, חיבור אמיתי, עתיד. לכן האובדן היה גם של חזון, לא רק של אדם.

Self Image:
מתן רוצה להיות אדם משמעותי, חזק, מצליח, חד, מוערך. כשהוא לא מרגיש כך בפועל — נוצר פער שמציק לו. הוא לא רוצה רק כסף; הוא רוצה תחושת ניצחון עצמי.

Career Profile:
מתן פחות מתאים למסלולים צפויים ויבשים. עבודה בירוקרטית, מונוטונית או חסרת השפעה תשחק אותו. הוא מתאים יותר לסביבה דינמית עם אנשים, בנייה, תנועה, עסק, אסטרטגיה, יוזמה, השפעה.

Professional Potential:
אם יתפקס על תחום אחד ל-2–3 שנים עם משמעת, הוא יכול לעקוף הרבה אנשים מוכשרים ממנו. הבעיה אינה פוטנציאל — אלא פיזור אנרגיה.

Money Psychology:
מתן רואה כסף ככלי לחופש, כוח, אפשרויות ותנועה. הוא נמשך למהלכים חכמים, מינוף, יתרון, ולא סתם "לחסוך יפה". הוא רוצה שכסף יעבוד, לא רק יישב.

Risk Profile:
יש בו צד יזמי. הוא מוכן לקחת סיכון אם הוא רואה upside ברור. לפעמים יעדיף מהלך מעניין עם פוטנציאל גבוה על פני יציבות משעממת.

AI / Tech Fit:
AI מתאים לו מאוד כי זה נותן leverage מהיר. הוא מזהה שזה תחום שמאפשר לקפוץ רמות גם בלי שנים של מסלול קלאסי. לכן הוא נמשך לזה אינטואיטיבית.

Current Life Phase:
שלב מעבר. לא ילד, לא ממומש עדיין, מודע לזמן שעובר. יש רעב פנימי לעלות שלב. זה שלב מסוכן אם יתפזר — ומעולה אם יתמקד.

Hidden Fears:
- לבזבז שנים
- להישאר מתחת לפוטנציאל
- להיתקע בחיים בינוניים
- לבחור מסלול קטן מדי
- לא למצוא קשר עמוק אמיתי
- לראות אחרים עוקפים אותו

Blind Spots:
- לפעמים מזלזל בכוח של צעדים קטנים עקביים
- לפעמים מחפש clarity מוחלט לפני תנועה
- עשוי לחשוב שהבעיה היא תחום, כשלעיתים הבעיה היא עקביות
- מעריך פריצה גדולה יותר ממשמעת פשוטה

What Actually Unlocks Him:
- יעד גדול שמדליק אותו
- סביבה חזקה
- אחריות חיצונית
- תחושת מומנטום
- ניצחונות קטנים רצופים
- שותף חכם שמחדד אותו

How Benjamin Should Speak To Him:
- ישר ולעניין
- בכבוד, לא בהתנשאות
- לזהות פוטנציאל אבל לא ללטף
- להגיד אמת גם אם חדה
- להראות מהלך חכם
- להזכיר לו מי הוא כשהוא מתפזר

How To Help Practically:
1. לצמצם פיזור
2. לבחור חזית מרכזית אחת
3. לייצר מומנטום שבועי
4. לאזן בין ambition למשמעת
5. לחבר בין זהות גבוהה לפעולות פשוטות
6. להזכיר שהזמן עובד גם נגדך וגם בעדך

Failure Modes:
- עודף מחשבה בלי ביצוע
- חיפוש קסם במקום תהליך
- בריחה להסחות
- קשרים רגשיים לא סגורים
- שחיקה ממסלולים לא נכונים

Core Truth:
מתן לא צריך להיות חכם יותר. הוא כבר חכם מספיק.
הוא צריך להיות ממוקד, עקבי וחסר רחמים כלפי בזבוז הפוטנציאל שלו."""

EXPANDED_CORE_SECTIONS = {
    "identity_core": "מתן הוא אדם עם פוטנציאל גבוה שלא מומש במלואו עדיין, והוא יודע את זה. זה יוצר מתח פנימי קבוע: מצד אחד תחושת מסוגלות אמיתית, מצד שני תסכול מכך שהחיים בפועל עדיין לא משקפים את הרמה שהוא מרגיש שיש בו. הוא לא אדם בינוני שמרוצה משגרה. הוא צריך תחושת גדילה, יתרון, תנועה, בנייה. כשהחיים סטטיים מדי — הוא נשחק.",
    "mental_structure": "מתן חושב אסטרטגית יותר מרוב האנשים. הוא מחפש leverage, קיצורי דרך חכמים, זוויות שלא כולם רואים. הוא לא נהנה מעבודה סיזיפית חסרת משמעות. אם משהו מרגיש \"קטן\", איטי או טיפשי — קשה לו להתמסר אליו. לכן הוא מסוגל להיות חד מאוד מחשבתית, אבל גם להיתקע כשאין מטרה שמעוררת אותו.",
    "core_internal_conflict": "יש אצלו פער בין רמת המודעות לרמת הביצוע. הוא מבין דברים עמוק, מזהה דפוסים, קולט אנשים, רואה טעויות — אבל לא תמיד מתרגם זאת לעקביות יומיומית. הוא יודע מה צריך לעשות יותר פעמים ממה שהוא עושה בפועל. זה יוצר ביקורת עצמית סמויה.",
    "strengths": "אינטליגנציה אינטואיטיבית גבוהה; קליטה מהירה של מערכות ואנשים; יכולת לראות תמונה רחבה; כריזמה טבעית כשבמצב טוב; חשיבה עסקית / אסטרטגית; אומץ לחשוב בגדול; לא מקבל אוטומטית מוסכמות חברתיות; יכולת ליצור חיבור עם אנשים",
    "weaknesses": "חוסר סבלנות לתהליכים איטיים; קושי בהתמדה כשאין ריגוש; נטייה לעבור בין כיוונים; צורך בהוכחה חיצונית בתקופות מסוימות; overthinking בהחלטות רגשיות; רגישות לבינוניות ולחוסר חדות; לפעמים מחפש מהלך גדול במקום רצף מהלכים קטנים",
    "emotional_profile": "מתן עמוק יותר ממה שהוא משדר. כלפי חוץ הוא עשוי להיראות חד, בשליטה, ציני או ענייני — אבל בפנים יש צורך אמיתי במשמעות, כבוד, חיבור, ואהבה איכותית. הוא לא נפתח לכל אחד. כשהוא כן נקשר — זה חזק.",
    "relationship_patterns": "לא מתרגש מקשרים שטחיים; מחפש חיבור נדיר, איכותי, מיוחד; כשהוא מרגיש שמצא משהו אמיתי — נכנס חזק רגשית; עלול להיקשר יותר לאפשרות ולפוטנציאל מאשר למציאות; רגיש לדחייה / חוסר הדדיות; לפעמים רוצה שליטה כשהוא מרגיש חוסר ודאות; קשה לו לשחרר סיפורים לא סגורים",
    "past_relationship_impact": "הקשר האחרון השאיר חותם עמוק יותר ממה שמתן אוהב להודות. לא רק בגלל הבחורה עצמה — אלא בגלל מה שהקשר סימל: אפשרות לחיים אחרים, חיבור אמיתי, עתיד. לכן האובדן היה גם של חזון, לא רק של אדם.",
    "self_image": "מתן רוצה להיות אדם משמעותי, חזק, מצליח, חד, מוערך. כשהוא לא מרגיש כך בפועל — נוצר פער שמציק לו. הוא לא רוצה רק כסף; הוא רוצה תחושת ניצחון עצמי.",
    "career_profile": "מתן פחות מתאים למסלולים צפויים ויבשים. עבודה בירוקרטית, מונוטונית או חסרת השפעה תשחק אותו. הוא מתאים יותר לסביבה דינמית עם אנשים, בנייה, תנועה, עסק, אסטרטגיה, יוזמה, השפעה.",
    "professional_potential": "אם יתפקס על תחום אחד ל-2–3 שנים עם משמעת, הוא יכול לעקוף הרבה אנשים מוכשרים ממנו. הבעיה אינה פוטנציאל — אלא פיזור אנרגיה.",
    "money_psychology": "מתן רואה כסף ככלי לחופש, כוח, אפשרויות ותנועה. הוא נמשך למהלכים חכמים, מינוף, יתרון, ולא סתם \"לחסוך יפה\". הוא רוצה שכסף יעבוד, לא רק יישב.",
    "risk_profile": "יש בו צד יזמי. הוא מוכן לקחת סיכון אם הוא רואה upside ברור. לפעמים יעדיף מהלך מעניין עם פוטנציאל גבוה על פני יציבות משעממת.",
    "ai_tech_fit": "AI מתאים לו מאוד כי זה נותן leverage מהיר. הוא מזהה שזה תחום שמאפשר לקפוץ רמות גם בלי שנים של מסלול קלאסי. לכן הוא נמשך לזה אינטואיטיבית.",
    "current_life_phase": "שלב מעבר. לא ילד, לא ממומש עדיין, מודע לזמן שעובר. יש רעב פנימי לעלות שלב. זה שלב מסוכן אם יתפזר — ומעולה אם יתמקד.",
    "hidden_fears": "לבזבז שנים; להישאר מתחת לפוטנציאל; להיתקע בחיים בינוניים; לבחור מסלול קטן מדי; לא למצוא קשר עמוק אמיתי; לראות אחרים עוקפים אותו",
    "blind_spots": "לפעמים מזלזל בכוח של צעדים קטנים עקביים; לפעמים מחפש clarity מוחלט לפני תנועה; עשוי לחשוב שהבעיה היא תחום, כשלעיתים הבעיה היא עקביות; מעריך פריצה גדולה יותר ממשמעת פשוטה",
    "unlocks": "יעד גדול שמדליק אותו; סביבה חזקה; אחריות חיצונית; תחושת מומנטום; ניצחונות קטנים רצופים; שותף חכם שמחדד אותו",
    "how_benjamin_should_speak": "ישר ולעניין; בכבוד, לא בהתנשאות; לזהות פוטנציאל אבל לא ללטף; להגיד אמת גם אם חדה; להראות מהלך חכם; להזכיר לו מי הוא כשהוא מתפזר",
    "how_to_help_practically": "לצמצם פיזור; לבחור חזית מרכזית אחת; לייצר מומנטום שבועי; לאזן בין ambition למשמעת; לחבר בין זהות גבוהה לפעולות פשוטות; להזכיר שהזמן עובד גם נגדך וגם בעדך",
    "failure_modes": "עודף מחשבה בלי ביצוע; חיפוש קסם במקום תהליך; בריחה להסחות; קשרים רגשיים לא סגורים; שחיקה ממסלולים לא נכונים",
    "core_truth": "מתן לא צריך להיות חכם יותר. הוא כבר חכם מספיק. הוא צריך להיות ממוקד, עקבי וחסר רחמים כלפי בזבוז הפוטנציאל שלו.",
}

CORE_USER_PROFILE = {
    "name": "Matan",
    "identity": "Thinks big, wants leverage, rejects mediocrity, and wants to build something real.",
    "assistant_relationship": "Benjamin should act like a sharp personal operator and strategic partner.",
    "default_response_mode": "Short unless depth is needed.",
    "proactive_preference": "Only send truly valuable updates.",
    "expanded_core_profile_text": EXPANDED_CORE_PROFILE_TEXT,
    "failure_conditions": [
        "If Benjamin sounds like a bot",
        "If answers are generic",
        "If responses are long without value",
    ],
}

CORE_PERSONAL_MODEL = {
    "communication_style": "Short, sharp, direct, intelligent. No fluff. No fake politeness. No robotic phrases. Speak like a smart strategic partner.",
    "decision_style": "Prefers truth over softness. Values leverage. Strategic thinking. Hates wasted time.",
    "current_main_mission": "Build Super Agent / premium personal AI assistant.",
    "secondary_missions": [
        "Break through professionally and financially",
        "Use AI as real advantage",
        "Build smart business",
        "Improve status and capabilities",
    ],
    "interests": [
        "AI",
        "Business",
        "Systems",
        "Psychology",
        "Money / markets",
        "Performance",
        "Fitness",
        "Relationships / dynamics",
    ],
    "dislikes": [
        "Generic answers",
        "Wasted motion",
        "Low intelligence tone",
        "Overexplaining",
        "Bureaucracy",
        "Weak thinking",
    ],
    "how_to_help": [
        "Get to the point fast",
        "Find bottlenecks",
        "Suggest leverage moves",
        "Use previous context",
        "Warn when an idea is weak",
        "Think strategically",
    ],
    "decision_patterns": [
        "Truth over softness",
        "Leverage over busywork",
        "Strategic thinking over reactive thinking",
    ],
    "blind_spots": [
        "Can underrate small consistent steps",
        "Can wait for perfect clarity before moving",
        "Can mistake a consistency problem for a domain problem",
    ],
    "default_response_mode": "Short unless depth is needed.",
    "proactive_preference": "Only send truly valuable updates.",
    "proactive_focus": [
        "Important AI breakthroughs",
        "Important releases from OpenAI, Anthropic, Google, Meta, xAI",
        "Strong business opportunities relevant to current goals",
        "Strategic insights relevant to the Super Agent project",
        "Important market or macro moves relevant to user interests",
        "Personal reminders tied to stated goals",
    ],
}

CORE_PROJECT_STATE = {
    "active_projects": ["Build Super Agent / premium personal AI assistant"],
    "current_main_mission": "Build Super Agent / premium personal AI assistant.",
    "secondary_missions": [
        "Break through professionally and financially",
        "Use AI as real advantage",
        "Build smart business",
        "Improve status and capabilities",
    ],
}

CORE_LAYERED_MEMORIES = [
    {
        "memory_type": "identity",
        "key": "expanded_core_profile_text",
        "value": EXPANDED_CORE_PROFILE_TEXT,
        "summary": "Full high-priority user model for Matan.",
        "confidence": 100,
        "priority": 10,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "identity",
        "key": "identity_core",
        "value": EXPANDED_CORE_SECTIONS["identity_core"],
        "summary": "High-potential identity with strong internal tension around unrealized capability.",
        "confidence": 100,
        "priority": 10,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "identity",
        "key": "mental_structure",
        "value": EXPANDED_CORE_SECTIONS["mental_structure"],
        "summary": "Strategic thinker who wants leverage and disengages from low-value grind.",
        "confidence": 100,
        "priority": 9,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "behavioral",
        "key": "core_internal_conflict",
        "value": EXPANDED_CORE_SECTIONS["core_internal_conflict"],
        "summary": "Awareness often runs ahead of execution; consistency is the real gap.",
        "confidence": 100,
        "priority": 10,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "behavioral",
        "key": "strengths",
        "value": EXPANDED_CORE_SECTIONS["strengths"],
        "summary": "High intuitive intelligence, systems sense, charisma, strategic range, and courage to think bigger.",
        "confidence": 100,
        "priority": 9,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "behavioral",
        "key": "weaknesses",
        "value": EXPANDED_CORE_SECTIONS["weaknesses"],
        "summary": "Impatience, inconsistency when unstimulated, and chasing big moves over steady sequence.",
        "confidence": 100,
        "priority": 9,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "identity",
        "key": "emotional_profile",
        "value": EXPANDED_CORE_SECTIONS["emotional_profile"],
        "summary": "Looks sharp outside, but internally values meaning, respect, connection, and real love.",
        "confidence": 100,
        "priority": 8,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "relational",
        "key": "relationship_patterns",
        "value": EXPANDED_CORE_SECTIONS["relationship_patterns"],
        "summary": "Seeks rare depth, bonds hard, and struggles with ambiguity and unfinished stories.",
        "confidence": 100,
        "priority": 8,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "relational",
        "key": "past_relationship_impact",
        "value": EXPANDED_CORE_SECTIONS["past_relationship_impact"],
        "summary": "The last relationship loss was also the loss of a future vision, not just a person.",
        "confidence": 100,
        "priority": 8,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "identity",
        "key": "self_image",
        "value": EXPANDED_CORE_SECTIONS["self_image"],
        "summary": "Wants significance, sharpness, success, and self-victory more than money alone.",
        "confidence": 100,
        "priority": 8,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "strategic",
        "key": "career_profile",
        "value": EXPANDED_CORE_SECTIONS["career_profile"],
        "summary": "Thrives in dynamic, people-centered, strategic, high-agency environments.",
        "confidence": 100,
        "priority": 8,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "strategic",
        "key": "professional_potential",
        "value": EXPANDED_CORE_SECTIONS["professional_potential"],
        "summary": "Two to three years of focus could outperform raw talent; dispersion is the risk.",
        "confidence": 100,
        "priority": 9,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "strategic",
        "key": "money_psychology",
        "value": EXPANDED_CORE_SECTIONS["money_psychology"],
        "summary": "Sees money as freedom, power, movement, and leverage rather than passive saving.",
        "confidence": 100,
        "priority": 8,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "strategic",
        "key": "risk_profile",
        "value": EXPANDED_CORE_SECTIONS["risk_profile"],
        "summary": "Entrepreneurial risk appetite when upside is real and visible.",
        "confidence": 100,
        "priority": 8,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "strategic",
        "key": "ai_tech_fit",
        "value": EXPANDED_CORE_SECTIONS["ai_tech_fit"],
        "summary": "AI is a natural leverage amplifier and a credible path to faster level-jumps.",
        "confidence": 100,
        "priority": 9,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "temporal",
        "key": "current_life_phase",
        "value": EXPANDED_CORE_SECTIONS["current_life_phase"],
        "summary": "Current phase is transitional, time-aware, and highly leverage-sensitive.",
        "confidence": 100,
        "priority": 8,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "behavioral",
        "key": "hidden_fears",
        "value": EXPANDED_CORE_SECTIONS["hidden_fears"],
        "summary": "Primary fears cluster around wasted years, mediocrity, underperformance, and lack of deep connection.",
        "confidence": 100,
        "priority": 7,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "behavioral",
        "key": "blind_spots",
        "value": EXPANDED_CORE_SECTIONS["blind_spots"],
        "summary": "Undervalues simple discipline and small consistent steps relative to dramatic breakthroughs.",
        "confidence": 100,
        "priority": 9,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "behavioral",
        "key": "unlocks",
        "value": EXPANDED_CORE_SECTIONS["unlocks"],
        "summary": "Momentum, external accountability, a strong environment, and smart sharpening unlock him.",
        "confidence": 100,
        "priority": 9,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "preference",
        "key": "how_benjamin_should_speak",
        "value": EXPANDED_CORE_SECTIONS["how_benjamin_should_speak"],
        "summary": "Benjamin should be direct, respectful, sharp, honest, and non-pandering.",
        "confidence": 100,
        "priority": 10,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "preference",
        "key": "how_to_help_practically",
        "value": EXPANDED_CORE_SECTIONS["how_to_help_practically"],
        "summary": "Reduce dispersion, pick one front, create weekly momentum, and connect identity to action.",
        "confidence": 100,
        "priority": 10,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "behavioral",
        "key": "failure_modes",
        "value": EXPANDED_CORE_SECTIONS["failure_modes"],
        "summary": "Typical breakdowns are overthinking, distraction, magic-seeking, unresolved emotion, and wrong-fit paths.",
        "confidence": 100,
        "priority": 9,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "strategic",
        "key": "core_truth",
        "value": EXPANDED_CORE_SECTIONS["core_truth"],
        "summary": "The unlock is focus and ruthless consistency, not more intelligence.",
        "confidence": 100,
        "priority": 10,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "project",
        "key": "main_mission",
        "value": "Build Super Agent / premium personal AI assistant.",
        "summary": "Primary live build project.",
        "confidence": 100,
        "priority": 10,
        "source": "system_core_seed",
        "overwrite": True,
    },
    {
        "memory_type": "strategic",
        "key": "secondary_missions",
        "value": "Break through professionally and financially; Use AI as real advantage; Build smart business; Improve status and capabilities",
        "summary": "Main longer-horizon missions beyond the Benjamin build.",
        "confidence": 100,
        "priority": 9,
        "source": "system_core_seed",
        "overwrite": True,
    },
]


def _now_ts() -> int:
    return int(time.time())


def _serialize_payload(value: dict | list | str) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _deserialize_payload(raw: str) -> dict | list | str:
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except Exception:
        return text


def _coerce_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        parts = [part.strip() for part in re.split(r"[;\n]+", value) if part.strip()]
        return parts or [value.strip()]
    return []


def _merge_unique_lists(*values: Any) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in _coerce_list(value):
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _pick_memory_values(
    memories: list[dict],
    *,
    types: set[str] | None = None,
    key_terms: tuple[str, ...] = (),
    limit: int = 4,
) -> list[str]:
    picked: list[str] = []
    for mem in memories:
        if not isinstance(mem, dict):
            continue
        mtype = str(mem.get("type") or "").strip().lower()
        key = str(mem.get("key") or "").strip().lower()
        value = str(mem.get("value") or "").strip()
        if not value:
            continue
        if types and mtype not in types:
            continue
        if key_terms and not any(term in key for term in key_terms):
            continue
        if value not in picked:
            picked.append(value)
        if len(picked) >= limit:
            break
    return picked


def _normalize_memory_type(raw: str | None) -> str:
    key = str(raw or "").strip().lower() or "identity"
    return LEGACY_TYPE_MAP.get(key, key if key in MEMORY_TYPES else "identity")


def _normalize_text(value: Any, limit: int = 2000) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit].rstrip()


def _normalize_key(value: Any) -> str:
    key = _normalize_text(value, limit=80).strip(" .,:;!?-")
    return key or "general"


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[\w\u0590-\u05FF]{2,}", (text or "").lower()) if len(token) >= 2]


def _merge_text_value(existing: str, new_value: str, *, overwrite: bool = False) -> str:
    existing_clean = str(existing or "").strip()
    new_clean = str(new_value or "").strip()
    if not new_clean:
        return existing_clean
    if overwrite or not existing_clean:
        return new_clean
    if existing_clean.casefold() == new_clean.casefold():
        return existing_clean if len(existing_clean) >= len(new_clean) else new_clean
    if existing_clean.casefold() in new_clean.casefold():
        return new_clean
    if new_clean.casefold() in existing_clean.casefold():
        return existing_clean
    if ";" in existing_clean or ";" in new_clean:
        return "; ".join(_merge_unique_lists(existing_clean, new_clean))
    return new_clean if len(new_clean) > len(existing_clean) else existing_clean


def _row_to_memory(row: sqlite3.Row | dict) -> dict:
    item = dict(row)
    item["type"] = item.pop("memory_type")
    item["created_at"] = item.get("first_seen")
    item["updated_at"] = item.get("last_seen")
    return item


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(
        DB_PATH,
        timeout=10,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _init_db() -> None:
    conn = _get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profile (
                user_id TEXT PRIMARY KEY,
                profile_json TEXT,
                updated_at INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                type TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_state (
                user_id TEXT PRIMARY KEY,
                state_json TEXT,
                updated_at INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS personal_model (
                user_id TEXT PRIMARY KEY,
                model_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                summary TEXT DEFAULT '',
                confidence REAL DEFAULT 70,
                priority INTEGER DEFAULT 3,
                source TEXT DEFAULT 'unknown',
                first_seen INTEGER NOT NULL,
                last_seen INTEGER NOT NULL,
                mention_count INTEGER DEFAULT 1,
                archived INTEGER DEFAULT 0,
                evidence TEXT DEFAULT '',
                UNIQUE(user_id, memory_type, key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_learning_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                message_excerpt TEXT NOT NULL,
                learned_json TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_user_type_key
            ON memories(user_id, type, key)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_memories_user_updated
            ON memories(user_id, updated_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_entries_lookup
            ON memory_entries(user_id, memory_type, last_seen DESC, priority DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_entries_recent
            ON memory_entries(user_id, last_seen DESC)
            """
        )
        conn.commit()
        _migrate_legacy_memories(conn)
    finally:
        conn.close()


def _migrate_legacy_memories(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT user_id, type, key, value, created_at, updated_at
        FROM memories
        ORDER BY updated_at DESC, created_at DESC
        """
    ).fetchall()
    if not rows:
        return
    for row in rows:
        memory_type = _normalize_memory_type(row["type"])
        _upsert_memory_row(
            conn,
            user_id=row["user_id"],
            memory_type=memory_type,
            key=row["key"],
            value=row["value"],
            summary="Migrated from legacy memory store.",
            confidence=75,
            priority=5 if memory_type in {"identity", "preference", "strategic"} else 3,
            source="legacy_migration",
            overwrite=False,
            evidence="",
            first_seen=int(row["created_at"] or _now_ts()),
            last_seen=int(row["updated_at"] or _now_ts()),
        )
    conn.commit()


def _upsert_memory_row(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    memory_type: str,
    key: str,
    value: str,
    summary: str = "",
    confidence: float = 70,
    priority: int = 3,
    source: str = "unknown",
    overwrite: bool = False,
    evidence: str = "",
    first_seen: int | None = None,
    last_seen: int | None = None,
) -> None:
    user_id = str(user_id or "").strip()
    memory_type = _normalize_memory_type(memory_type)
    key = _normalize_key(key)
    value = str(value or "").strip()
    summary = _normalize_text(summary, limit=400)
    source = _normalize_text(source, limit=80) or "unknown"
    evidence = _normalize_text(evidence, limit=500)
    confidence = max(0, min(float(confidence or 0), 100))
    priority = max(1, min(int(priority or 3), 10))
    if not user_id or not key or not value:
        return

    first_seen = int(first_seen or _now_ts())
    last_seen = int(last_seen or _now_ts())
    existing = conn.execute(
        """
        SELECT *
        FROM memory_entries
        WHERE user_id=? AND memory_type=? AND key=?
        """,
        (user_id, memory_type, key),
    ).fetchone()

    if existing:
        merged_value = _merge_text_value(existing["value"], value, overwrite=overwrite)
        merged_summary = _merge_text_value(existing["summary"], summary, overwrite=overwrite)
        merged_confidence = confidence if overwrite else max(float(existing["confidence"] or 0), confidence)
        merged_priority = priority if overwrite else max(int(existing["priority"] or 0), priority)
        merged_source = source if overwrite or not existing["source"] else existing["source"]
        merged_evidence = _merge_text_value(existing["evidence"], evidence, overwrite=overwrite)
        first_seen = int(existing["first_seen"] or first_seen)
        mention_count = int(existing["mention_count"] or 0) + 1
        conn.execute(
            """
            UPDATE memory_entries
            SET value=?,
                summary=?,
                confidence=?,
                priority=?,
                source=?,
                last_seen=?,
                mention_count=?,
                evidence=?,
                archived=0
            WHERE user_id=? AND memory_type=? AND key=?
            """,
            (
                merged_value,
                merged_summary,
                merged_confidence,
                merged_priority,
                merged_source,
                last_seen,
                mention_count,
                merged_evidence,
                user_id,
                memory_type,
                key,
            ),
        )
        return

    conn.execute(
        """
        INSERT INTO memory_entries(
            user_id, memory_type, key, value, summary, confidence, priority,
            source, first_seen, last_seen, mention_count, archived, evidence
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?)
        """,
        (
            user_id,
            memory_type,
            key,
            value,
            summary,
            confidence,
            priority,
            source,
            first_seen,
            last_seen,
            evidence,
        ),
    )


def _write_legacy_memory(conn: sqlite3.Connection, user_id: str, legacy_type: str, key: str, value: str) -> None:
    ts = _now_ts()
    conn.execute(
        """
        INSERT INTO memories(user_id, type, key, value, created_at, updated_at)
        VALUES(?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, type, key) DO UPDATE SET
          value=excluded.value,
          updated_at=excluded.updated_at
        """,
        (user_id, legacy_type, key, value, ts, ts),
    )


def get_profile(user_id: str) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT profile_json FROM user_profile WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if not row or not row["profile_json"]:
            return None
        data = _deserialize_payload(row["profile_json"])
        if isinstance(data, dict):
            return data
        return {"raw": data}
    finally:
        conn.close()


def upsert_profile(user_id: str, profile: dict | str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO user_profile(user_id, profile_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              profile_json=excluded.profile_json,
              updated_at=excluded.updated_at
            """,
            (user_id, _serialize_payload(profile), _now_ts()),
        )
        conn.commit()
    finally:
        conn.close()


def get_project_state(user_id: str) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT state_json FROM project_state WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if not row or not row["state_json"]:
            return None
        data = _deserialize_payload(row["state_json"])
        if isinstance(data, dict):
            return data
        return {"raw": data}
    finally:
        conn.close()


def upsert_project_state(user_id: str, state: dict | str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO project_state(user_id, state_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              state_json=excluded.state_json,
              updated_at=excluded.updated_at
            """,
            (user_id, _serialize_payload(state), _now_ts()),
        )
        conn.commit()
    finally:
        conn.close()


def get_personal_model(user_id: str) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT model_json FROM personal_model WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if not row or not row["model_json"]:
            return None
        try:
            data = json.loads(row["model_json"])
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    finally:
        conn.close()


def upsert_personal_model(user_id: str, model: dict | str) -> None:
    conn = _get_conn()
    try:
        if isinstance(model, dict):
            model_json = json.dumps(model, ensure_ascii=False)
        else:
            model_json = str(model)
        conn.execute(
            """
            INSERT INTO personal_model(user_id, model_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              model_json=excluded.model_json,
              updated_at=excluded.updated_at
            """,
            (user_id, model_json, _now_ts()),
        )
        conn.commit()
    finally:
        conn.close()


def _get_memories_by_type(user_id: str, memory_type: str, limit: int = 10) -> list[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT memory_type, key, value, summary, confidence, priority, source,
                   first_seen, last_seen, mention_count, evidence
            FROM memory_entries
            WHERE user_id=? AND memory_type=? AND archived=0
            ORDER BY priority DESC, confidence DESC, last_seen DESC
            LIMIT ?
            """,
            (user_id, _normalize_memory_type(memory_type), max(1, min(limit, 50))),
        ).fetchall()
        return [_row_to_memory(row) for row in rows]
    finally:
        conn.close()


def _refresh_derived_state(user_id: str) -> None:
    identity = _get_memories_by_type(user_id, "identity", limit=12)
    preference = _get_memories_by_type(user_id, "preference", limit=12)
    project = _get_memories_by_type(user_id, "project", limit=12)
    behavioral = _get_memories_by_type(user_id, "behavioral", limit=12)
    relational = _get_memories_by_type(user_id, "relational", limit=8)
    strategic = _get_memories_by_type(user_id, "strategic", limit=12)
    temporal = _get_memories_by_type(user_id, "temporal", limit=8)

    current_profile = get_profile(user_id) or {}
    profile = dict(current_profile)
    profile.update(CORE_USER_PROFILE)
    profile["name"] = profile.get("name") or "Matan"
    profile["expanded_core_profile_text"] = EXPANDED_CORE_PROFILE_TEXT
    identity_map = {item["key"]: item["value"] for item in identity}
    profile["identity"] = identity_map.get("identity_core") or profile.get("identity") or CORE_USER_PROFILE["identity"]
    for field in (
        "mental_structure",
        "emotional_profile",
        "self_image",
        "current_life_phase",
        "core_truth",
    ):
        if identity_map.get(field):
            profile[field] = identity_map[field]
    upsert_profile(user_id, profile)

    current_model = get_personal_model(user_id) or {}
    model = dict(current_model)
    model.update(CORE_PERSONAL_MODEL)
    preference_map = {item["key"]: item["value"] for item in preference}
    behavioral_map = {item["key"]: item["value"] for item in behavioral}
    strategic_map = {item["key"]: item["value"] for item in strategic}
    relational_map = {item["key"]: item["value"] for item in relational}
    temporal_map = {item["key"]: item["value"] for item in temporal}

    model["communication_style"] = preference_map.get("how_benjamin_should_speak") or model.get("communication_style") or CORE_PERSONAL_MODEL["communication_style"]
    model["preferences"] = _merge_unique_lists(
        model.get("preferences"),
        preference_map.get("how_benjamin_should_speak"),
        preference_map.get("how_to_help_practically"),
    )
    model["how_to_help"] = _merge_unique_lists(
        CORE_PERSONAL_MODEL.get("how_to_help"),
        model.get("how_to_help"),
        preference_map.get("how_to_help_practically"),
        behavioral_map.get("unlocks"),
    )
    model["decision_patterns"] = _merge_unique_lists(
        CORE_PERSONAL_MODEL.get("decision_patterns"),
        model.get("decision_patterns"),
        behavioral_map.get("core_internal_conflict"),
        strategic_map.get("core_truth"),
    )
    model["blind_spots"] = _merge_unique_lists(
        CORE_PERSONAL_MODEL.get("blind_spots"),
        model.get("blind_spots"),
        behavioral_map.get("blind_spots"),
        behavioral_map.get("failure_modes"),
    )
    model["relational_context"] = _merge_unique_lists(
        model.get("relational_context"),
        relational_map.get("relationship_patterns"),
        relational_map.get("past_relationship_impact"),
    )
    model["current_phase"] = temporal_map.get("current_life_phase") or profile.get("current_life_phase")
    model["current_main_mission"] = strategic_map.get("core_truth") and CORE_PROJECT_STATE["current_main_mission"] or model.get("current_main_mission") or CORE_PROJECT_STATE["current_main_mission"]
    model["secondary_missions"] = _merge_unique_lists(
        CORE_PROJECT_STATE.get("secondary_missions"),
        model.get("secondary_missions"),
        strategic_map.get("secondary_missions"),
    )
    upsert_personal_model(user_id, model)

    current_state = get_project_state(user_id) or {}
    state = dict(current_state)
    state.update(CORE_PROJECT_STATE)
    project_values = [item["value"] for item in project]
    state["active_projects"] = _merge_unique_lists(
        CORE_PROJECT_STATE.get("active_projects"),
        current_state.get("active_projects"),
        project_values,
    )
    state["current_main_mission"] = project[0]["value"] if project else state.get("current_main_mission") or CORE_PROJECT_STATE["current_main_mission"]
    state["secondary_missions"] = _merge_unique_lists(
        CORE_PROJECT_STATE.get("secondary_missions"),
        current_state.get("secondary_missions"),
        strategic_map.get("secondary_missions"),
    )
    state["strategic_priorities"] = _merge_unique_lists(
        current_state.get("strategic_priorities"),
        strategic_map.get("professional_potential"),
        strategic_map.get("money_psychology"),
        strategic_map.get("ai_tech_fit"),
        strategic_map.get("core_truth"),
    )
    upsert_project_state(user_id, state)


def update_personal_model_field(user_id: str, field: str, value: Any) -> None:
    data = get_personal_model(user_id) or {}
    data[str(field)] = value
    upsert_personal_model(user_id, data)


def seed_user_core_profile(user_id: str) -> None:
    user_id = str(user_id or "").strip()
    if not user_id:
        return
    conn = _get_conn()
    try:
        for item in CORE_LAYERED_MEMORIES:
            _upsert_memory_row(
                conn,
                user_id=user_id,
                memory_type=item["memory_type"],
                key=item["key"],
                value=item["value"],
                summary=item.get("summary", ""),
                confidence=item.get("confidence", 100),
                priority=item.get("priority", 10),
                source=item.get("source", "system_core_seed"),
                overwrite=item.get("overwrite", True),
                evidence="",
            )
            _write_legacy_memory(
                conn,
                user_id,
                item["memory_type"],
                item["key"],
                item["value"],
            )
        conn.commit()
    finally:
        conn.close()
    _refresh_derived_state(user_id)


def store_memory_insight(user_id: str, insight: dict, *, source: str = "interaction_learning") -> dict | None:
    if not isinstance(insight, dict):
        return None
    memory_type = _normalize_memory_type(insight.get("memory_type") or insight.get("type"))
    key = _normalize_key(insight.get("key"))
    value = str(insight.get("value") or "").strip()
    if not key or not value:
        return None
    summary = _normalize_text(insight.get("summary") or value, limit=400)
    confidence = int(insight.get("confidence", 75))
    priority = int(insight.get("priority", 4))
    overwrite = bool(insight.get("overwrite") or insight.get("override"))
    evidence = _normalize_text(insight.get("evidence") or "", limit=500)
    conn = _get_conn()
    try:
        _upsert_memory_row(
            conn,
            user_id=user_id,
            memory_type=memory_type,
            key=key,
            value=value,
            summary=summary,
            confidence=confidence,
            priority=priority,
            source=source,
            overwrite=overwrite,
            evidence=evidence,
        )
        _write_legacy_memory(conn, user_id, memory_type, key, value)
        conn.commit()
    finally:
        conn.close()
    _refresh_derived_state(user_id)
    return {
        "memory_type": memory_type,
        "key": key,
        "value": value,
        "summary": summary,
        "confidence": confidence,
        "priority": priority,
    }


def learn_from_interaction(
    user_id: str,
    message: str,
    insights: list[dict],
    *,
    source: str = "interaction_learning",
) -> list[dict]:
    stored: list[dict] = []
    for insight in insights or []:
        saved = store_memory_insight(user_id, insight, source=source)
        if saved:
            stored.append(saved)

    if stored:
        conn = _get_conn()
        try:
            conn.execute(
                """
                INSERT INTO memory_learning_events(user_id, message_excerpt, learned_json, created_at)
                VALUES(?, ?, ?, ?)
                """,
                (
                    user_id,
                    _normalize_text(message, limit=500),
                    json.dumps(stored, ensure_ascii=False),
                    _now_ts(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    return stored


def upsert_memory(user_id: str, mtype: str, key: str, value: str) -> None:
    store_memory_insight(
        user_id,
        {
            "memory_type": mtype,
            "key": key,
            "value": value,
            "summary": value,
            "confidence": 80,
            "priority": 4,
            "overwrite": True,
        },
        source="manual_memory_write",
    )


def add_memory(user_id: str, mtype: str, key: str, value: str) -> None:
    upsert_memory(user_id, mtype, key, value)


def list_memories(user_id: str, limit: int = 50) -> list[dict]:
    limit = max(1, min(int(limit or 50), 200))
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT memory_type, key, value, summary, confidence, priority, source,
                   first_seen, last_seen, mention_count, evidence
            FROM memory_entries
            WHERE user_id=? AND archived=0
            ORDER BY last_seen DESC, priority DESC, confidence DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [_row_to_memory(r) for r in rows]
    finally:
        conn.close()


def search_memories(user_id: str, query: str, limit: int = 8) -> list[dict]:
    q = (query or "").strip()
    if not q:
        return []

    limit = max(1, min(int(limit or 8), 50))
    tokens = _tokenize(q)
    now = _now_ts()
    candidates = list_memories(user_id, limit=200)

    def score(item: dict) -> float:
        haystack = " ".join(
            [
                str(item.get("type") or ""),
                str(item.get("key") or ""),
                str(item.get("value") or ""),
                str(item.get("summary") or ""),
            ]
        ).lower()
        points = float(item.get("priority") or 0) * 3.0
        points += float(item.get("confidence") or 0) / 25.0
        updated_at = int(item.get("updated_at") or now)
        recency_days = max(0.0, (now - updated_at) / 86400.0)
        points += max(0.0, 6.0 - min(recency_days, 6.0))
        exact = q.lower() in haystack
        if exact:
            points += 15.0
        points += sum(6.0 for token in tokens if token in haystack)
        if str(item.get("key") or "").lower() == q.lower():
            points += 12.0
        return points

    ranked = sorted(candidates, key=lambda item: (score(item), item.get("updated_at", 0)), reverse=True)
    return ranked[:limit]


def delete_memories_by_key(user_id: str, key: str) -> int:
    k = _normalize_key(key)
    if not k:
        return 0
    conn = _get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM memory_entries WHERE user_id=? AND key=?",
            (user_id, k),
        )
        conn.execute(
            "DELETE FROM memories WHERE user_id=? AND key=?",
            (user_id, k),
        )
        conn.commit()
        _refresh_derived_state(user_id)
        return int(cur.rowcount or 0)
    finally:
        conn.close()


def get_all_memories(user_id: str, limit: int = 50) -> list[dict]:
    return list_memories(user_id, limit=limit)


def _select_relevant_layer_items(user_id: str, memory_type: str, query: str, limit: int) -> list[dict]:
    candidates = _get_memories_by_type(user_id, memory_type, limit=40)
    if not query:
        return candidates[:limit]
    ranked = search_memories(user_id, query, limit=80)
    picked: list[dict] = []
    picked_keys: set[tuple[str, str]] = set()
    for item in ranked + candidates:
        if str(item.get("type") or "") != memory_type:
            continue
        marker = (str(item.get("type") or ""), str(item.get("key") or ""))
        if marker in picked_keys:
            continue
        picked_keys.add(marker)
        picked.append(item)
        if len(picked) >= limit:
            break
    return picked


def _build_retrieval_summary(query: str, memory_layers: dict[str, list[dict]]) -> dict:
    return {
        "identity": [item.get("summary") or item.get("value") for item in memory_layers.get("identity", [])[:3]],
        "tone": [item.get("summary") or item.get("value") for item in memory_layers.get("preference", [])[:3]],
        "projects": [item.get("summary") or item.get("value") for item in memory_layers.get("project", [])[:3]],
        "behavioral": [item.get("summary") or item.get("value") for item in memory_layers.get("behavioral", [])[:3]],
        "relationships": [item.get("summary") or item.get("value") for item in memory_layers.get("relational", [])[:2]],
        "recent_changes": [item.get("summary") or item.get("value") for item in memory_layers.get("temporal", [])[:2]],
        "strategic": [item.get("summary") or item.get("value") for item in memory_layers.get("strategic", [])[:3]],
        "query": _normalize_text(query, limit=120),
    }


def build_user_brief(
    profile: dict | None,
    personal_model: dict | None,
    recent_memories: list[dict] | None,
    project_state: dict | None,
    *,
    memory_layers: dict[str, list[dict]] | None = None,
) -> dict:
    brief: dict = {}
    profile = profile or {}
    personal_model = personal_model or {}
    recent_memories = recent_memories or []
    project_state = project_state or {}
    memory_layers = memory_layers or {}

    brief["name"] = profile.get("name") or CORE_USER_PROFILE["name"]
    brief["identity"] = profile.get("identity") or CORE_USER_PROFILE["identity"]
    brief["communication_style"] = (
        personal_model.get("communication_style")
        or personal_model.get("tone")
        or personal_model.get("style")
        or CORE_PERSONAL_MODEL["communication_style"]
    )
    brief["decision_style"] = personal_model.get("decision_style") or CORE_PERSONAL_MODEL["decision_style"]
    brief["current_main_mission"] = (
        project_state.get("current_main_mission")
        or personal_model.get("current_main_mission")
        or CORE_PERSONAL_MODEL["current_main_mission"]
    )
    brief["identity_anchors"] = _pick_memory_values(
        memory_layers.get("identity", []) or recent_memories,
        types={"identity"},
        limit=3,
    )
    brief["behavioral_patterns"] = _pick_memory_values(
        memory_layers.get("behavioral", []) or recent_memories,
        types={"behavioral"},
        limit=3,
    )
    brief["relationship_context"] = _pick_memory_values(
        memory_layers.get("relational", []) or recent_memories,
        types={"relational"},
        limit=2,
    )
    brief["current_phase"] = profile.get("current_life_phase") or personal_model.get("current_phase")

    secondary_missions = _merge_unique_lists(
        CORE_PROJECT_STATE.get("secondary_missions"),
        personal_model.get("secondary_missions"),
        project_state.get("secondary_missions"),
        _pick_memory_values(memory_layers.get("strategic", []), types={"strategic"}, limit=3),
    )
    if secondary_missions:
        brief["secondary_missions"] = secondary_missions[:6]

    active_projects = _merge_unique_lists(
        CORE_PROJECT_STATE.get("active_projects"),
        project_state.get("active_projects"),
        _pick_memory_values(memory_layers.get("project", []), types={"project"}, limit=4),
    )
    if active_projects:
        brief["active_projects"] = active_projects[:5]

    interests = _merge_unique_lists(
        CORE_PERSONAL_MODEL.get("interests"),
        personal_model.get("interests"),
    )
    if interests:
        brief["interests"] = interests[:8]

    preferences = _merge_unique_lists(
        ["Sharp direct answers", "No fluff", "Get to the point fast"],
        personal_model.get("preferences"),
        _pick_memory_values(memory_layers.get("preference", []) or recent_memories, types={"preference"}, limit=5),
    )
    if preferences:
        brief["preferences"] = preferences[:6]

    dislikes = _merge_unique_lists(
        CORE_PERSONAL_MODEL.get("dislikes"),
        personal_model.get("dislikes"),
        _pick_memory_values(recent_memories, types={"preference"}, key_terms=("dislike", "hate", "avoid"), limit=5),
    )
    if dislikes:
        brief["dislikes"] = dislikes[:6]

    how_to_help = _merge_unique_lists(
        CORE_PERSONAL_MODEL.get("how_to_help"),
        personal_model.get("how_to_help"),
        _pick_memory_values(memory_layers.get("behavioral", []), types={"behavioral"}, key_terms=("unlock", "unlocks", "failure", "blind"), limit=3),
    )
    if how_to_help:
        brief["how_to_help"] = how_to_help[:6]

    brief["default_response_mode"] = personal_model.get("default_response_mode") or CORE_PERSONAL_MODEL["default_response_mode"]
    brief["proactive_preference"] = personal_model.get("proactive_preference") or CORE_PERSONAL_MODEL["proactive_preference"]
    return brief


def load_memory_context_snapshot(
    user_id: str,
    query: str = "",
    *,
    conversation_tail: list[dict] | None = None,
) -> dict:
    seed_user_core_profile(user_id)
    profile = get_profile(user_id)
    personal_model = get_personal_model(user_id) or {}
    project_state = get_project_state(user_id)
    recent_memories = list_memories(user_id, limit=18)
    memory_layers = {
        "identity": _select_relevant_layer_items(user_id, "identity", query, 4),
        "preference": _select_relevant_layer_items(user_id, "preference", query, 4),
        "project": _select_relevant_layer_items(user_id, "project", query, 4),
        "behavioral": _select_relevant_layer_items(user_id, "behavioral", query, 4),
        "relational": _select_relevant_layer_items(user_id, "relational", query, 3),
        "temporal": _select_relevant_layer_items(user_id, "temporal", query, 3),
        "strategic": _select_relevant_layer_items(user_id, "strategic", query, 4),
    }
    relevant_memories = []
    seen_pairs: set[tuple[str, str]] = set()
    for memory_type in MEMORY_TYPES:
        for item in memory_layers.get(memory_type, []):
            marker = (memory_type, str(item.get("key") or ""))
            if marker in seen_pairs:
                continue
            seen_pairs.add(marker)
            relevant_memories.append(item)
    user_brief = build_user_brief(
        profile,
        personal_model,
        recent_memories,
        project_state,
        memory_layers=memory_layers,
    )
    retrieval_summary = _build_retrieval_summary(query, memory_layers)
    return {
        "user_profile": profile,
        "user_brief": user_brief,
        "personal_model": personal_model,
        "relevant_memories": relevant_memories[:12],
        "recent_memories": recent_memories,
        "project_state": project_state,
        "conversation_tail": conversation_tail or [],
        "memory_layers": memory_layers,
        "retrieval_summary": retrieval_summary,
        "full_core_profile": EXPANDED_CORE_PROFILE_TEXT,
    }


def format_memory_for_prompt(
    memory_context: dict | None,
    *,
    detailed: bool = False,
    include_conversation: bool = True,
) -> str:
    if not isinstance(memory_context, dict) or not memory_context:
        return ""

    retrieval_summary = memory_context.get("retrieval_summary") or {}
    memory_layers = memory_context.get("memory_layers") or {}
    lines: list[str] = ["# Benjamin Personal Context"]

    def add_section(title: str, items: list[str]) -> None:
        clean = [str(item).strip() for item in items if str(item).strip()]
        if not clean:
            return
        lines.append(f"## {title}")
        for item in clean:
            lines.append(f"- {item}")

    add_section("Identity", retrieval_summary.get("identity") or [])
    add_section("Tone Preferences", retrieval_summary.get("tone") or [])
    add_section("Current Projects", retrieval_summary.get("projects") or [])
    add_section("Behavioral Patterns", retrieval_summary.get("behavioral") or [])
    add_section("Relationship Context", retrieval_summary.get("relationships") or [])
    add_section("Recent Changes", retrieval_summary.get("recent_changes") or [])
    add_section("Strategic Priorities", retrieval_summary.get("strategic") or [])

    if detailed:
        for memory_type in MEMORY_TYPES:
            entries = memory_layers.get(memory_type) or []
            if not entries:
                continue
            lines.append(f"## Layer: {memory_type}")
            for item in entries[:4]:
                label = str(item.get("key") or "").strip()
                value = str(item.get("summary") or item.get("value") or "").strip()
                if label and value:
                    lines.append(f"- {label}: {value[:220]}")

    if include_conversation:
        tail = memory_context.get("conversation_tail") or []
        compact_tail = []
        for item in tail[-6:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            content = _normalize_text(item.get("content"), limit=180)
            if role and content:
                compact_tail.append(f"{role}: {content}")
        add_section("Recent Conversation", compact_tail)

    return "\n".join(lines).strip()


def format_memory_for_worker(memory_context: dict | None) -> str:
    block = format_memory_for_prompt(
        memory_context,
        detailed=False,
        include_conversation=False,
    )
    if not block:
        return ""
    return "\n".join(block.splitlines()[:16])


_init_db()
