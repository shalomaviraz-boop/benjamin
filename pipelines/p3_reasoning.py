"""P3: Deep reasoning - GPT → [Claude Review if High-risk] → User."""
from experts.gpt_client import GPTClient
from experts.claude_client import ClaudeClient
from utils.helpers import is_high_risk

gpt = GPTClient()
claude = ClaudeClient()


async def run(message: str, context: str = "") -> str:
    """P3: Deep reasoning with optional Claude review for high-risk."""

    # 1. GPT generates initial response
    prompt = f"""Analyze and answer thoughtfully:

Question: {message}
{f"Context: {context}" if context else ""}

Provide a clear, reasoned response. Consider multiple angles.
"""
    content = await gpt.generate(prompt)

    # 2. High-risk? → Claude review
    if is_high_risk(message):
        review = await claude.review_advice(message, content)
        content = f"{content}\n\n--- בדיקה נוספת ---\n{review}"

    # 3. Final voice pass
    return await gpt.voice_pass(content, expert_name="Reasoning")
