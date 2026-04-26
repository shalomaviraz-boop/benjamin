# Benjamin V1

Benjamin is a Telegram-first personal AI assistant built around a single GPT brain, an evolving user model, durable SQLite memory, and a lightweight learning layer.

## What V1 includes

- Async Telegram bot
- GPT-driven judgment and response generation
- Seeded user model for מתן that evolves over time
- SQLite memory for identity, goals, preferences, struggles, projects, priorities, and important context
- Rich seeded core profile for מתן stored persistently under `Matan primary user`
- Conversation logging
- Learning from natural conversation without manual memory commands
- Honest behavior when certainty or live data is missing

## Project structure

```text
bot.py
config.py
benjamin_brain.py
memory.py
learning.py
prompts.py
user_model.py
requirements.txt
.env.example
README.md
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env` with:

- `TELEGRAM_TOKEN`
- `OPENAI_API_KEY`

Optional:

- `OPENAI_MODEL` defaults to `gpt-5.5`
- `OPENAI_ANALYSIS_MODEL` defaults to the same model
- `DATABASE_PATH` defaults to `benjamin_memory.db`
- `PRIMARY_USER_ID` defaults to `Matan primary user`
- `BENJAMIN_SINGLE_USER_MODE` defaults to `true`

## Run locally

```bash
python bot.py
```

## How Benjamin works

Each incoming Telegram message goes through this flow:

1. Ensure the user profile exists and seed it with the initial model for מתן.
2. Log the conversation turn.
3. Retrieve relevant memories from SQLite.
4. Run a GPT judgment pass to decide intent, tone, depth, memory relevance, and whether the request needs live data.
5. Generate the actual reply with GPT using profile, memory, judgment, and recent conversation.
6. Run a GPT learning pass to infer durable updates and store them without bloating memory.

If structured parsing fails, Benjamin falls back to heuristics instead of crashing.

On startup, Benjamin seeds a strong structured core profile for מתן into SQLite and derives a compact set of high-value memories from it. In single-user mode, Telegram conversations resolve to that canonical profile key so Benjamin starts with real context and keeps learning forward from there.

## Render deployment

Deploy this as a Render Worker service.

- Build command: `pip install -r requirements.txt`
- Start command: `python bot.py`

Set the same environment variables from `.env.example` in Render's dashboard.

## Notes

- V1 does not pretend to have live web access.
- Memory is stored locally in SQLite.
- The architecture stays clean so tools, specialists, or multi-agent orchestration can be added later without rewriting the core.
