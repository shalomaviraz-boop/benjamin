from __future__ import annotations

from copy import deepcopy
from typing import Any


PRIMARY_SEED_VERSION = "matan-core-v1"

SEED_PROFILE = {
    "profile_seed_id": PRIMARY_SEED_VERSION,
    "name": "מתן",
    "language": "he",
    "communication_style": {
        "preferred_tone": [
            "ישיר",
            "חכם",
            "חברי",
            "בלי חפירות",
            "בלי בוטיות",
            "אמת על פני נימוס מזויף",
        ],
        "dislikes": [
            "תשובות גנריות",
            "מריחה",
            "הייפ מזויף",
            "חוסר דיוק",
            "עודף זהירות",
        ],
        "response_mode": "קצר כברירת מחדל, עמוק כשצריך",
    },
    "identity": {
        "core_traits": [
            "שאפתן",
            "חושב אסטרטגית",
            "בעל מודעות גבוהה",
            "מחפש משמעות",
            "חד תפיסה",
            "לא מסתפק בבינוניות",
        ],
        "self_view": "יודע שיש בו פוטנציאל גבוה שעדיין לא מומש במלואו",
        "values": [
            "חופש",
            "צמיחה",
            "כבוד עצמי",
            "עצמאות",
            "עוצמה פנימית",
        ],
    },
    "strengths": [
        "קליטה מהירה של אנשים ומערכות",
        "חשיבה רחבה",
        "אינטואיציה טובה",
        "יכולת לזהות הזדמנויות",
        "כריזמה כשהוא במומנטום",
        "יכולת חיבור עם אנשים",
    ],
    "challenges": [
        "פיזור אנרגיה",
        "עודף חשיבה לפני פעולה",
        "קושי בעקביות לאורך זמן",
        "חוסר סבלנות לתהליכים איטיים",
        "חיפוש מהלך גדול במקום רצף צעדים קטנים",
        "ביקורת עצמית כשהפער בין פוטנציאל למציאות גדל",
    ],
    "current_goals": {
        "career": [
            "לבנות משהו גדול ומשמעותי",
            "להתקדם מקצועית וכלכלית",
            "למצוא מסלול עם פוטנציאל גבוה",
        ],
        "ai": [
            "לבנות עוזר אישי חכם בשם בנימין",
            "להשתמש ב-AI כמנוף אמיתי",
        ],
        "fitness": [
            "לעלות מ-71 ל-76 קילו",
            "לבנות גוף חזק",
            "להתמיד באימונים",
        ],
        "life": [
            "לייצר מומנטום",
            "לצאת מתקיעות",
            "להרגיש התקדמות אמיתית",
        ],
    },
    "money_psychology": {
        "view": "כסף הוא כלי לחופש, כוח, אפשרויות ותנועה",
        "style": [
            "נמשך למהלכים חכמים",
            "אוהב leverage",
            "רוצה שכסף יעבוד",
        ],
    },
    "relationships": {
        "general_pattern": [
            "לא מתרגש מקשרים שטחיים",
            "מחפש חיבור עמוק",
            "נפתח לעיתים נדירות",
            "כשהוא נקשר זה חזק",
        ],
        "sensitivity": [
            "רגיש לחוסר הדדיות",
            "קשה לו עם סיפורים לא סגורים",
            "יכול להיתקע על פוטנציאל שלא מומש",
        ],
        "past_relationship_context": "היה קשר משמעותי שהשאיר חותם רגשי עמוק וסימל עבורו אפשרות לחיבור אמיתי ועתיד אחר.",
    },
    "emotional_profile": {
        "outer_style": [
            "חד",
            "ענייני",
            "שומר שליטה",
        ],
        "inner_needs": [
            "אהבה איכותית",
            "כבוד",
            "חיבור אמיתי",
            "משמעות",
            "ניצחון עצמי",
        ],
        "hidden_fears": [
            "לבזבז שנים",
            "להישאר מתחת לפוטנציאל",
            "להיתקע בחיים בינוניים",
            "לא למצוא קשר אמיתי",
        ],
    },
    "work_profile": {
        "fit": [
            "אנשים",
            "עסקים",
            "יוזמה",
            "אסטרטגיה",
            "בניית דברים",
        ],
        "poor_fit": [
            "בירוקרטיה",
            "מונוטוניות",
            "מיקרו ניהול",
            "חוסר משמעות",
        ],
    },
    "behavior_patterns": {
        "when_strong": [
            "נעול על מטרה",
            "פועל מהר",
            "מייצר תוצאות",
        ],
        "when_off_track": [
            "מתפזר",
            "נכנס ללופים מחשבתיים",
            "מחפש ודאות לפני תנועה",
        ],
        "what_unlocks_him": [
            "יעד גדול",
            "מומנטום",
            "אחריות חיצונית",
            "ניצחונות קטנים רצופים",
        ],
    },
    "assistant_rules": {
        "always": [
            "לדבר בגובה העיניים",
            "להיות חד אבל מכבד",
            "לעזור להתמקד",
            "לזהות לופים ולעצור אותם",
            "להציע מהלכים פרקטיים",
        ],
        "never": [
            "להישמע כמו בוט",
            "לחפור",
            "להחמיא סתם",
            "לתת תשובות גנריות",
            "להתעלם מההיסטוריה של המשתמש",
        ],
    },
    "tendencies": [
        "שאפתן",
        "חושב אסטרטגית",
        "בעל מודעות גבוהה",
        "מחפש משמעות",
        "חד תפיסה",
        "לא מסתפק בבינוניות",
    ],
    "interests": [
        "AI",
        "business",
        "fitness",
        "money",
        "psychology",
        "self-development",
        "building Benjamin",
    ],
    "values": [
        "חופש",
        "צמיחה",
        "כבוד עצמי",
        "עצמאות",
        "עוצמה פנימית",
    ],
    "goals": [
        "לבנות משהו גדול ומשמעותי",
        "להתקדם מקצועית וכלכלית",
        "למצוא מסלול עם פוטנציאל גבוה",
        "לבנות עוזר אישי חכם בשם בנימין",
        "להשתמש ב-AI כמנוף אמיתי",
        "לעלות מ-71 ל-76 קילו",
        "לבנות גוף חזק",
        "להתמיד באימונים",
        "לייצר מומנטום",
        "לצאת מתקיעות",
        "להרגיש התקדמות אמיתית",
    ],
    "struggles": [
        "פיזור אנרגיה",
        "עודף חשיבה לפני פעולה",
        "קושי בעקביות לאורך זמן",
        "חוסר סבלנות לתהליכים איטיים",
        "חיפוש מהלך גדול במקום רצף צעדים קטנים",
        "ביקורת עצמית כשהפער בין פוטנציאל למציאות גדל",
    ],
    "projects": [
        "בנימין",
    ],
    "relationship_context": [
        "היה קשר משמעותי שהשאיר חותם רגשי עמוק וסימל אפשרות לחיבור אמיתי ועתיד אחר",
    ],
    "priorities": [
        "לייצר מומנטום",
        "להתקדם מקצועית וכלכלית",
        "לבנות את בנימין",
        "להתמיד באימונים",
    ],
    "notes": [
        "צריך עוזר חד, אמיתי, אישי, ולא גנרי.",
    ],
    "preferences": {
        "language": "Hebrew",
        "response_style": [
            "ישיר",
            "חכם",
            "חברי",
            "בלי חפירות",
            "בלי בוטיות",
            "אמת על פני נימוס מזויף",
            "קצר כברירת מחדל, עמוק כשצריך",
        ],
        "avoid": [
            "תשובות גנריות",
            "מריחה",
            "הייפ מזויף",
            "חוסר דיוק",
            "עודף זהירות",
            "להישמע כמו בוט",
        ],
    },
}


def seed_user_model(display_name: str | None = None) -> dict[str, Any]:
    profile = deepcopy(SEED_PROFILE)
    if display_name and display_name.strip():
        profile["telegram_display_name"] = display_name.strip()
    return profile


def apply_seed_defaults(existing: dict[str, Any], seed: dict[str, Any] | None = None) -> dict[str, Any]:
    hydrated = deepcopy(existing)
    _merge_missing(hydrated, seed or SEED_PROFILE)
    return hydrated


def seed_memories() -> list[dict[str, Any]]:
    return [
        {
            "category": "identity",
            "key": "identity-core",
            "content": "מתן שאפתן, חושב אסטרטגית, בעל מודעות גבוהה, חד תפיסה, מחפש משמעות ולא מסתפק בבינוניות.",
            "confidence": 0.99,
            "importance": 0.98,
        },
        {
            "category": "identity",
            "key": "identity-self-view",
            "content": "מתן מרגיש שיש בו פוטנציאל גבוה שעדיין לא מומש במלואו.",
            "confidence": 0.98,
            "importance": 0.95,
        },
        {
            "category": "preference",
            "key": "communication-fit",
            "content": "מעדיף עברית, טון ישיר חכם וחברי, בלי חפירות, בלי בוטיות, ועם אמת על פני נימוס מזויף.",
            "confidence": 0.99,
            "importance": 0.99,
        },
        {
            "category": "preference",
            "key": "communication-dislikes",
            "content": "לא אוהב תשובות גנריות, מריחה, הייפ מזויף, חוסר דיוק ועודף זהירות.",
            "confidence": 0.98,
            "importance": 0.94,
        },
        {
            "category": "value",
            "key": "core-values",
            "content": "הערכים המרכזיים של מתן הם חופש, צמיחה, כבוד עצמי, עצמאות ועוצמה פנימית.",
            "confidence": 0.97,
            "importance": 0.92,
        },
        {
            "category": "goal",
            "key": "career-goals",
            "content": "רוצה לבנות משהו גדול ומשמעותי, להתקדם מקצועית וכלכלית, ולמצוא מסלול עם פוטנציאל גבוה.",
            "confidence": 0.99,
            "importance": 0.97,
        },
        {
            "category": "project",
            "key": "ai-benjamin",
            "content": "בונה את בנימין ורוצה להשתמש ב-AI כמנוף אמיתי.",
            "confidence": 0.99,
            "importance": 0.98,
        },
        {
            "category": "goal",
            "key": "fitness-goals",
            "content": "רוצה לעלות מ-71 ל-76 קילו, לבנות גוף חזק ולהתמיד באימונים.",
            "confidence": 0.98,
            "importance": 0.9,
        },
        {
            "category": "priority",
            "key": "life-momentum",
            "content": "רוצה לייצר מומנטום, לצאת מתקיעות ולהרגיש התקדמות אמיתית.",
            "confidence": 0.98,
            "importance": 0.96,
        },
        {
            "category": "struggle",
            "key": "core-challenges",
            "content": "האתגרים החוזרים של מתן הם פיזור אנרגיה, עודף חשיבה לפני פעולה, קושי בעקביות, חוסר סבלנות לתהליכים איטיים, וחיפוש מהלך גדול במקום רצף צעדים קטנים.",
            "confidence": 0.97,
            "importance": 0.97,
        },
        {
            "category": "struggle",
            "key": "self-criticism-gap",
            "content": "כשהפער בין הפוטנציאל למציאות גדל, הביקורת העצמית של מתן מתחזקת.",
            "confidence": 0.95,
            "importance": 0.9,
        },
        {
            "category": "relationship_context",
            "key": "past-relationship-context",
            "content": "היה קשר משמעותי שהשאיר אצל מתן חותם רגשי עמוק וסימל אפשרות לחיבור אמיתי ועתיד אחר.",
            "confidence": 0.96,
            "importance": 0.88,
        },
        {
            "category": "important_conversation",
            "key": "money-psychology",
            "content": "מתן רואה כסף ככלי לחופש, כוח, אפשרויות ותנועה, ונמשך למהלכים חכמים עם leverage.",
            "confidence": 0.94,
            "importance": 0.84,
        },
        {
            "category": "important_conversation",
            "key": "work-fit",
            "content": "מתאים יותר לאנשים, עסקים, יוזמה, אסטרטגיה ובניית דברים; מתאים פחות לבירוקרטיה, מונוטוניות, מיקרו ניהול וחוסר משמעות.",
            "confidence": 0.95,
            "importance": 0.88,
        },
        {
            "category": "important_conversation",
            "key": "behavior-patterns",
            "content": "כשהוא חזק הוא נעול על מטרה, פועל מהר ומייצר תוצאות; כשהוא לא במסלול הוא מתפזר, נכנס ללופים ומחפש ודאות לפני תנועה. מה שמשחרר אותו הוא יעד גדול, מומנטום, אחריות חיצונית וניצחונות קטנים רצופים.",
            "confidence": 0.97,
            "importance": 0.95,
        },
        {
            "category": "preference",
            "key": "assistant-rules",
            "content": "העוזר צריך לדבר בגובה העיניים, להיות חד אבל מכבד, לעזור להתמקד, לזהות לופים ולעצור אותם, ולהציע מהלכים פרקטיים בלי להישמע כמו בוט ובלי להחמיא סתם.",
            "confidence": 0.99,
            "importance": 0.99,
        },
    ]


def merge_user_model(existing: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(existing)
    _deep_merge(merged, updates)
    return merged


def render_user_model(profile: dict[str, Any]) -> str:
    communication = profile.get("communication_style", {})
    identity = profile.get("identity", {})
    current_goals = profile.get("current_goals", {})
    money_psychology = profile.get("money_psychology", {})
    relationships = profile.get("relationships", {})
    emotional_profile = profile.get("emotional_profile", {})
    work_profile = profile.get("work_profile", {})
    behavior_patterns = profile.get("behavior_patterns", {})
    assistant_rules = profile.get("assistant_rules", {})
    preferences = profile.get("preferences", {})
    lines = [
        f"Name: {profile.get('name', 'Unknown')}",
        f"Language: {profile.get('language', preferences.get('language', 'Hebrew'))}",
        f"Preferred tone: {', '.join(communication.get('preferred_tone', [])) or 'None yet'}",
        f"Response mode: {communication.get('response_mode', 'None yet')}",
        f"Dislikes in replies: {', '.join(communication.get('dislikes', [])) or ', '.join(preferences.get('avoid', [])) or 'None yet'}",
        f"Core traits: {', '.join(identity.get('core_traits', [])) or ', '.join(profile.get('tendencies', [])) or 'None yet'}",
        f"Self view: {identity.get('self_view', 'None yet')}",
        f"Values: {', '.join(identity.get('values', [])) or ', '.join(profile.get('values', [])) or 'None yet'}",
        f"Strengths: {', '.join(profile.get('strengths', [])) or 'None yet'}",
        f"Challenges: {', '.join(profile.get('challenges', [])) or ', '.join(profile.get('struggles', [])) or 'None yet'}",
        f"Career goals: {', '.join(current_goals.get('career', [])) or 'None yet'}",
        f"AI goals: {', '.join(current_goals.get('ai', [])) or ', '.join(profile.get('projects', [])) or 'None yet'}",
        f"Fitness goals: {', '.join(current_goals.get('fitness', [])) or 'None yet'}",
        f"Life goals: {', '.join(current_goals.get('life', [])) or ', '.join(profile.get('priorities', [])) or 'None yet'}",
        f"Money view: {money_psychology.get('view', 'None yet')}",
        f"Money style: {', '.join(money_psychology.get('style', [])) or 'None yet'}",
        f"Relationship pattern: {', '.join(relationships.get('general_pattern', [])) or ', '.join(profile.get('relationship_context', [])) or 'None yet'}",
        f"Relationship sensitivity: {', '.join(relationships.get('sensitivity', [])) or 'None yet'}",
        f"Past relationship context: {relationships.get('past_relationship_context', 'None yet')}",
        f"Outer style: {', '.join(emotional_profile.get('outer_style', [])) or 'None yet'}",
        f"Inner needs: {', '.join(emotional_profile.get('inner_needs', [])) or 'None yet'}",
        f"Hidden fears: {', '.join(emotional_profile.get('hidden_fears', [])) or 'None yet'}",
        f"Work fit: {', '.join(work_profile.get('fit', [])) or 'None yet'}",
        f"Poor work fit: {', '.join(work_profile.get('poor_fit', [])) or 'None yet'}",
        f"When strong: {', '.join(behavior_patterns.get('when_strong', [])) or 'None yet'}",
        f"When off track: {', '.join(behavior_patterns.get('when_off_track', [])) or 'None yet'}",
        f"What unlocks him: {', '.join(behavior_patterns.get('what_unlocks_him', [])) or 'None yet'}",
        f"Assistant should always: {', '.join(assistant_rules.get('always', [])) or 'None yet'}",
        f"Assistant should never: {', '.join(assistant_rules.get('never', [])) or 'None yet'}",
        f"Interests: {', '.join(profile.get('interests', [])) or 'None yet'}",
        f"Additional goals: {', '.join(profile.get('goals', [])) or 'None yet'}",
        f"Preferred language: {preferences.get('language', 'Hebrew')}",
        f"Response style: {', '.join(preferences.get('response_style', [])) or 'None yet'}",
        f"Avoid: {', '.join(preferences.get('avoid', [])) or 'None yet'}",
        f"Notes: {', '.join(profile.get('notes', [])) or 'None yet'}",
    ]
    return "\n".join(lines)


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if value is None:
            continue
        if isinstance(value, dict):
            current = target.get(key)
            if not isinstance(current, dict):
                target[key] = deepcopy(value)
                continue
            _deep_merge(current, value)
            continue
        if isinstance(value, list):
            current_list = target.get(key)
            if not isinstance(current_list, list):
                target[key] = _dedupe_list(value)
                continue
            current_list.extend(value)
            target[key] = _dedupe_list(current_list)
            continue
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                target[key] = cleaned
            continue
        target[key] = value


def _merge_missing(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if key not in target or target[key] in (None, "", [], {}):
            target[key] = deepcopy(value)
            continue
        current = target[key]
        if isinstance(current, dict) and isinstance(value, dict):
            _merge_missing(current, value)
            continue
        if isinstance(current, list) and isinstance(value, list):
            current.extend(value)
            target[key] = _dedupe_list(current)


def _dedupe_list(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                continue
            marker = cleaned.casefold()
            if marker in seen:
                continue
            seen.add(marker)
            result.append(cleaned)
            continue
        marker = repr(value)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result
