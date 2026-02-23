# בנימין - עוזר אישי חכם

Phase 1 MVP: Router חכם עם 4 Pipelines

## ארכיטקטורה

- **GPT-4** = Orchestrator (בוחר pipeline + voice pass סופי)
- **Gemini** = Web-grounded answers (Google Search)
- **Claude** = Code + Review

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# ערוך .env עם המפתחות שלך
python bot.py
```

## Pipelines

| Pipeline | שימוש | דוגמאות |
|----------|-------|---------|
| P1 | שאלות כלליות | "מה זה machine learning?" |
| P2 | עדכניות/עובדות | "מה מזג האוויר באוסלו", "מה שער דולר שקל" |
| P3 | החלטות, ניתוח | שאלות מורכבות |
| P4 | קוד | "כתוב פונקציה fibonacci" |

## Tests

- "מה מזג האוויר באוסלו" → P2
- "מה שער דולר שקל" → P2
- "כתוב פונקציה fibonacci" → P4
- "הסבר quantum computing" → P1/P3
- "מי זכה אתמול" → P2
