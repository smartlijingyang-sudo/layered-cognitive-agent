"""ask_user tool module — human-in-the-loop (lobe-user-interaction alignment)."""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.result import ApprovalPendingError
from lca.contracts.models.core.tool import ToolApi, ToolManifest, ToolMeta
from lca.contracts.protocols import Tool
from lca.infrastructure.tools.builder import build_tools_from_manifest

IDENTIFIER = "lobe-user-interaction"
_MAX_QUESTIONS = 4
_MAX_OPTIONS = 4

MANIFEST = ToolManifest(
    identifier=IDENTIFIER,
    type="builtin",
    api=(
        ToolApi(
            name="askUserQuestion",
            description=(
                "向用户提出结构化问题（可附带选项）。"
                "需要澄清意图、验证假设、或让用户做决策时使用。"
                "执行会暂停，等待用户回复。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "questions": {
                        "type": "array",
                        "description": "Questions to ask (1-4).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string", "description": "The question text."},
                                "header": {
                                    "type": "string",
                                    "description": "Short label (max 12 chars).",
                                },
                                "options": {
                                    "type": "array",
                                    "description": "Available choices (2-4).",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "label": {"type": "string"},
                                            "description": {"type": "string"},
                                        },
                                        "required": ["label", "description"],
                                    },
                                },
                                "multiSelect": {
                                    "type": "boolean",
                                    "description": "Allow multiple selections.",
                                },
                            },
                            "required": ["question", "header", "options"],
                        },
                    },
                },
                "required": ["questions"],
            },
            is_idempotent=True,
            default_timeout_ms=3_600_000,
        ),
    ),
    meta=ToolMeta(
        avatar="💬", title="Ask User", description="Human-in-the-loop structured questions"
    ),
)


class AskUserExecutor:
    def validate(self, api_name: str, args: dict[str, Any]) -> str | None:
        return _validate(args)

    async def askUserQuestion(self, params: dict[str, Any]) -> Observation:  # noqa: N802
        error = _validate(params)
        if error:
            return Observation(observation_id="", success=False, payload=None, error=error)
        raise ApprovalPendingError(
            approval_request={"type": "ask_user_question", "questions": params["questions"]}
        )


def _validate(args: dict[str, Any]) -> str | None:
    questions = args.get("questions")
    if not isinstance(questions, list) or not questions:
        return "questions must be a non-empty array"
    if len(questions) > _MAX_QUESTIONS:
        return f"questions array has {len(questions)} items, max {_MAX_QUESTIONS}"
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            return f"questions[{i}] must be an object"
        if not q.get("question"):
            return f"questions[{i}].question is required"
        opts = q.get("options", [])
        if not isinstance(opts, list) or len(opts) < 2:
            return f"questions[{i}].options must have at least 2 items"
        if len(opts) > _MAX_OPTIONS:
            return f"questions[{i}].options has {len(opts)} items, max {_MAX_OPTIONS}"
    return None


def build_tools() -> list[Tool]:
    return build_tools_from_manifest(MANIFEST, AskUserExecutor())
