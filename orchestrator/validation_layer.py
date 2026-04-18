"""Post-execution validation and fallback decisions."""

from __future__ import annotations

from typing import Any


class ValidationLayer:
    def validate(self, *, message: str, plan: dict, execution_plan: dict | None = None, result: Any = None) -> dict:
        text = ""
        if isinstance(result, str):
            text = result.strip()
        elif isinstance(result, dict):
            text = str(result.get("output") or result.get("final_answer") or result.get("result") or "").strip()

        task_type = str((plan or {}).get("task_type") or "").strip().lower()
        needs_output = task_type not in {"memory", "verification"}
        is_valid = True
        reasons: list[str] = []

        if needs_output and not text:
            is_valid = False
            reasons.append("empty_output")

        if isinstance(result, dict) and result.get("status") == "failed":
            is_valid = False
            reasons.append("agent_failed")

        if isinstance(result, dict) and result.get("approved") is False:
            is_valid = False
            reasons.append("verification_rejected")

        return {
            "is_valid": is_valid,
            "should_fallback": not is_valid,
            "final_output": text,
            "reasons": reasons,
            "task_type": task_type,
            "routing_source": str((plan or {}).get("routing_source") or "llm"),
            "agent_sequence": (execution_plan or {}).get("agent_sequence") or [],
            "summary": ", ".join(reasons) if reasons else "ok",
        }
