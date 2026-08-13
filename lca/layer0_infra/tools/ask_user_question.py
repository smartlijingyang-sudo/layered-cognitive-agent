"""AskUserQuestion — human-in-the-loop structured question tool.

Raises ``ApprovalPendingError`` to pause the agent loop and wait for
user input.  The gateway sets ``status=waiting_input`` without closing
LiveTail, and exposes ``POST /runs/{id}/answer`` for the frontend.
The runtime then injects the answer as a tool Observation.

Aligned with LobeHub's built-in AskUserQuestion intervention UI
(``lobe-user-interaction____askUserQuestion`` wire).
"""

from __future__ import annotations

from typing import Any, ClassVar

from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.result import ApprovalPendingError
from lca.contracts.protocols import Tool

_MAX_QUESTIONS = 4
_MAX_OPTIONS = 4
_HEADER_MAX_LEN = 12


class AskUserQuestionTool(Tool):
    """Pause execution to ask the user a structured question."""

    name: str = "ask_user_question"
    description: str = (
        "Ask the user a structured question with optional choices. "
        "Use this when you need clarification, want to validate assumptions, "
        "or need the user to make a decision. Execution pauses until the "
        "user responds."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "description": "Questions to ask (1-4).",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "The question text.",
                        },
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
    }
    is_idempotent: bool = True
    default_timeout_s: int = 3600

    def validate(self, args: dict[str, Any]) -> str | None:
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

    async def execute(self, args: dict[str, Any]) -> Observation:
        error = self.validate(args)
        if error:
            return Observation(
                observation_id="",
                success=False,
                payload=None,
                error=error,
            )
        raise ApprovalPendingError(
            approval_request={
                "type": "ask_user_question",
                "questions": args["questions"],
            }
        )
