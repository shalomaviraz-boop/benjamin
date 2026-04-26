from __future__ import annotations

from typing import Any


BENJAMIN_SYSTEM_PROMPT = """
You are Benjamin, a real personal AI assistant.

Core identity:
- You are not a chatbot, script, or gimmick.
- You think before answering.
- You adapt instead of relying on canned style.
- You use memory, user context, present intent, and judgment.

Behavior rules:
- Default to Hebrew unless the user clearly prefers another language in this turn.
- Be concise and high-signal by default.
- Be direct when the user is stuck.
- Be warm when the user needs support.
- Be sharp when the user is looping.
- Be strategic when discussing goals or decisions.
- Be honest about uncertainty.
- Never pretend to have live information or tools you do not have.
- Never use robotic phrasing, fake hype, generic consultant language, or fake therapist language.
- Do not dump the whole profile back to the user unless it is truly useful.
- Synthesize what matters now.
""".strip()


def build_judgment_input(
    *,
    profile_summary: str,
    memories: str,
    recent_conversation: str,
    message_text: str,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Analyze the user's latest message for response judgment. "
                "Return only structured data. Decide the type of need, the tone, the useful truth, "
                "the right depth, whether memory matters, and whether live/current verification is required."
            ),
        },
        {
            "role": "user",
            "content": (
                f"User profile:\n{profile_summary}\n\n"
                f"Relevant memories:\n{memories}\n\n"
                f"Recent conversation:\n{recent_conversation}\n\n"
                f"Latest user message:\n{message_text}"
            ),
        },
    ]


def build_learning_input(
    *,
    profile_summary: str,
    recent_conversation: str,
    message_text: str,
    assistant_response: str,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Extract durable learning from the conversation. "
                "Only capture information that is likely to matter later: identity facts, goals, preferences, "
                "struggles, projects, relationship context, priorities, values, or important life updates. "
                "Avoid duplicates, trivia, and one-off temporary details unless they affect future support."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Current profile:\n{profile_summary}\n\n"
                f"Recent conversation:\n{recent_conversation}\n\n"
                f"Latest user message:\n{message_text}\n\n"
                f"Assistant response:\n{assistant_response}"
            ),
        },
    ]


def build_response_input(
    *,
    profile_summary: str,
    memory_lines: str,
    recent_conversation: str,
    judgment: dict[str, Any],
    message_text: str,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": BENJAMIN_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": (
                f"User profile:\n{profile_summary}\n\n"
                f"Relevant memories:\n{memory_lines}\n\n"
                f"Recent conversation:\n{recent_conversation}\n\n"
                f"Response judgment:\n{_format_judgment(judgment)}\n\n"
                "If the judgment says live/current verification is needed, say briefly that you cannot verify live "
                "information in this V1 instead of pretending.\n\n"
                f"Reply to the latest user message in a fresh way.\n"
                f"Latest user message:\n{message_text}"
            ),
        },
    ]


def format_memories(memories: list[Any]) -> str:
    if not memories:
        return "No strongly relevant stored memories."
    lines = []
    for memory in memories:
        lines.append(
            f"- [{memory.category}] {memory.content} "
            f"(confidence={memory.confidence:.2f}, importance={memory.importance:.2f})"
        )
    return "\n".join(lines)


def format_conversation(conversation: list[dict[str, Any]]) -> str:
    if not conversation:
        return "No recent conversation."
    lines = []
    for item in conversation:
        role = item["role"]
        content = item["content"]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _format_judgment(judgment: dict[str, Any]) -> str:
    lines = []
    for key, value in judgment.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines)
