"""First-version execution agent for direct task execution."""

from agents.agent_context import read_shared_context
from agents.agent_contract import build_agent_result
from agents.base_agent import BaseAgent
from experts.model_router import model_router
from utils.benjamin_identity import build_benjamin_user_prompt


class ExecutionAgent(BaseAgent):
    def __init__(self):
        super().__init__("execution", "Executes task prompts using existing generation flow.")

    def _build_domain_prompt(self, message: str, plan: dict) -> str:
        capability = self.capabilities or {}
        responsibility = capability.get("responsibility") or self.description or self.name
        can_handle = ", ".join(capability.get("can_handle") or [])
        prompt = build_benjamin_user_prompt(message)
        return (
            f"{prompt}\n\n"
            "הנחיות פנימיות:\n"
            f"- תחום אחריות: {responsibility}\n"
            f"- תחום כיסוי: {can_handle}\n"
            "- תישאר חד, טבעי, קצר ופרקטי.\n"
            "- אל תישמע כמו בוט, יועץ גנרי, או שכבת תמיכה.\n"
            "- אל תכתוב: 'נכון ל...', 'להלן הצעה...', 'לסיכום...', 'איך זה מתקשר...', 'הנה גרסה מקצועית...'.\n"
            "- אם יש תשובה ברורה, תן אותה ישר. אם יש next step טוב, תן אותו ישר.\n"
            "- אל תזרוק לינקים או רשימות מקורות גולמיות אלא אם המשתמש ביקש.\n"
            "- אם הבקשה עמומה, קח את ההנחה הסבירה הכי מועילה ותתקדם.\n"
            f"- רמזי תכנון: use_web={bool(plan.get('use_web'))}, require_verification={bool(plan.get('require_verification'))}, require_code_review={bool(plan.get('require_code_review'))}\n"
        )

    async def run(self, task: dict, context: dict) -> dict:
        shared = read_shared_context(task, context)
        message = (shared.user_message or task.get("message") or "").strip()
        plan = shared.task or task.get("plan") or {}
        memory_context = shared.memory_context or (context or {}).get("memory_context")
        use_web = bool(plan.get("use_web"))

        if not message:
            result = build_agent_result(
                agent=self.name,
                status="failed",
                notes="missing task message",
                should_fallback=True,
                agent_context=shared.to_dict(),
            )
            shared.execution_output = result
            shared.add_log(self.name, "missing task message")
            result["agent_context"] = shared.to_dict()
            return result

        try:
            task_type = str(task.get("type") or self.name or "execution")
            web_mode = "news" if task_type in {"research", "ai_expert"} else "market" if task_type == "finance" else "research"
            prompt = self._build_domain_prompt(message, plan)
            output, provider = await model_router.generate(
                prompt=prompt,
                task_type=task_type,
                memory_context=memory_context,
                use_web=use_web,
                require_code_review=bool(plan.get("require_code_review")),
                require_verification=bool(plan.get("require_verification")),
                web_mode=web_mode,
            )
            result = build_agent_result(
                agent=self.name,
                output=output,
                notes=f"provider={provider}, use_web={use_web}",
                agent_context=shared.to_dict(),
            )
            shared.execution_output = result
            shared.final_output = output
            shared.add_log(self.name, f"execution success (use_web={use_web})")
            result["agent_context"] = shared.to_dict()
            return result
        except Exception as e:
            result = build_agent_result(
                agent=self.name,
                status="failed",
                notes=f"execution error: {e}",
                should_fallback=True,
                agent_context=shared.to_dict(),
            )
            shared.execution_output = result
            shared.add_log(self.name, f"execution failed: {e}")
            result["agent_context"] = shared.to_dict()
            return result
