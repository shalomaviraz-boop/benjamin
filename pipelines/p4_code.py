"""P4: Code - Claude write → GPT sanity → [Claude fix] → Claude review → GPT voice."""
from experts.claude_client import ClaudeClient
from experts.gpt_client import GPTClient
from utils.helpers import extract_issues

claude = ClaudeClient()
gpt = GPTClient()

MAX_ITERATIONS = 2


async def run(message: str) -> str:
    """P4: Code with review."""

    code = None
    issues = []

    for attempt in range(MAX_ITERATIONS):
        # 1. Claude writes
        if attempt == 0:
            code = await claude.write_code(message)
        else:
            code = await claude.write_code(message, fix_issues=issues)

        # 2. GPT sanity check
        sanity = await gpt.sanity_check(code, message)

        # 3. Check verdict
        verdict = "YES" if "VERDICT: YES" in sanity.upper() else "NO"

        if verdict == "YES":
            break

        issues = extract_issues(sanity)

        # Last iteration and still NO
        if attempt == MAX_ITERATIONS - 1:
            issues_str = "\n".join(f"- {i}" for i in issues) if issues else "לא זוהו"
            return f"""לא הצלחתי לוודא שהקוד מושלם לחלוטין.

הנה הקוד + בעיות שנותרו:
```python
{code}
```

בעיות פתוחות:
{issues_str}

מומלץ לבדוק ידנית לפני הרצה.
"""

    # 4. Claude review (different prompt!)
    review = await claude.review_code(code)

    # 5. GPT voice pass
    final = await gpt.voice_pass(
        content=f"```python\n{code}\n```",
        expert_name="Claude",
        review=review,
    )

    return final
