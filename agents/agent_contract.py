"""Unified agent contract helpers for Benjamin."""

from __future__ import annotations

from typing import Any

ALLOWED_STATUS = {"success", "failed", "not_implemented", "needs_input", "needs_approval"}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def build_agent_result(
    *,
    agent: str,
    status: str = "success",
    output: str = "",
    notes: str = "",
    should_fallback: bool = False,
    needs_revision: bool = False,
    approved: bool | None = None,
    data: dict | None = None,
    agent_context: dict | None = None,
) -> dict:
    status = status if status in ALLOWED_STATUS else "failed"
    result = {
        "agent": agent,
        "status": status,
        "output": _as_text(output),
        "notes": _as_text(notes),
        "should_fallback": bool(should_fallback),
        "needs_revision": bool(needs_revision),
        "data": data if isinstance(data, dict) else {},
        "agent_context": agent_context if isinstance(agent_context, dict) else {},
    }
    if approved is not None:
        result["approved"] = bool(approved)
    return result


def normalize_agent_result(agent_name: str, result: Any, *, fallback_note: str = "") -> dict:
    if not isinstance(result, dict):
        return build_agent_result(
            agent=agent_name,
            status="failed",
            notes=fallback_note or "invalid result type",
            should_fallback=True,
        )

    normalized = {
        "agent": result.get("agent") or agent_name,
        "status": result.get("status") or "success",
        "output": _as_text(result.get("output") or result.get("final_answer") or result.get("result") or ""),
        "notes": _as_text(result.get("notes") or ""),
        "should_fallback": bool(result.get("should_fallback", False)),
        "needs_revision": bool(result.get("needs_revision", False)),
        "data": result.get("data") if isinstance(result.get("data"), dict) else {},
        "agent_context": result.get("agent_context") if isinstance(result.get("agent_context"), dict) else {},
    }

    if normalized["status"] not in ALLOWED_STATUS:
        normalized["status"] = "failed"
    if "approved" in result:
        normalized["approved"] = bool(result.get("approved"))
    if "objective" in result:
        normalized["objective"] = _as_text(result.get("objective"))
    if isinstance(result.get("steps"), list):
        normalized["steps"] = [str(s).strip() for s in result.get("steps") if str(s).strip()]
    if isinstance(result.get("recommended_agent_sequence"), list):
        normalized["recommended_agent_sequence"] = [str(s).strip() for s in result.get("recommended_agent_sequence") if str(s).strip()]
    if "needs_research" in result:
        normalized["needs_research"] = bool(result.get("needs_research"))
    if "needs_verification" in result:
        normalized["needs_verification"] = bool(result.get("needs_verification"))
    return normalized
