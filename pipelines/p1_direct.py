"""P1: Direct answer - GPT only, no web/review."""
from experts.gpt_client import GPTClient

gpt = GPTClient()


async def run(message: str) -> str:
    """P1: Direct answer - GPT → User."""
    prompt = f"Answer this question clearly and accurately:\n{message}"
    content = await gpt.generate(prompt)
    return await gpt.voice_pass(content, expert_name="Direct")
