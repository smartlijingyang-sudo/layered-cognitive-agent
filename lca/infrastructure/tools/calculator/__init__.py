"""calculator tool module — safe arithmetic evaluator."""

from __future__ import annotations

import ast
import operator
import time
from typing import Any, ClassVar

from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.result import ToolInputError
from lca.contracts.models.core.tool import ToolApi, ToolManifest, ToolMeta
from lca.contracts.protocols import Tool
from lca.infrastructure.tools.builder import build_tools_from_manifest

IDENTIFIER = "calculator"

MANIFEST = ToolManifest(
    identifier=IDENTIFIER,
    type="builtin",
    api=(
        ToolApi(
            name="calculate",
            description="安全求值四则运算表达式（支持 + - * / // % ** 和一元 +/-）",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "纯算术表达式，如 '26 * 1.5 + 3'",
                    }
                },
                "required": ["expression"],
            },
            is_idempotent=True,
        ),
    ),
    meta=ToolMeta(
        avatar="🧮", title="Calculator", description="Safe arithmetic expression evaluator"
    ),
)


class CalculatorExecutor:
    _OPS: ClassVar[dict[type, Any]] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def validate(self, api_name: str, args: dict[str, Any]) -> str | None:
        expr = args.get("expression")
        if expr is None or (isinstance(expr, str) and not expr.strip()):
            return "表达式不能为空，请提供纯算术表达式，如 '26 * 1.5 + 3'"
        if not isinstance(expr, str):
            return f"表达式必须是字符串，实际类型: {type(expr).__name__}"
        return None

    async def calculate(self, params: dict[str, Any]) -> Observation:
        start = time.monotonic()
        expr = params.get("expression", "")
        if not isinstance(expr, str) or not expr.strip():
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error="表达式不能为空",
                latency_ms=latency_ms,
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )
        try:
            value = self._safe_eval(expr)
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"),
                success=True,
                payload=value,
                latency_ms=latency_ms,
            )
        except ToolInputError as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=str(e),
                latency_ms=latency_ms,
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )
        except (ValueError, OverflowError, ZeroDivisionError) as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=str(e),
                latency_ms=latency_ms,
            )

    def _safe_eval(self, expr: str) -> float:
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as e:
            raise ToolInputError(
                f"表达式语法错误 '{expr}': {e}。请提供纯算术表达式，如 '26 * 1.5 + 3'"
            ) from e
        return self._eval_node(tree.body)

    def _eval_node(self, node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in self._OPS:
            return float(
                self._OPS[type(node.op)](self._eval_node(node.left), self._eval_node(node.right))
            )
        if isinstance(node, ast.UnaryOp) and type(node.op) in self._OPS:
            return float(self._OPS[type(node.op)](self._eval_node(node.operand)))
        node_type = type(node).__name__
        supported = "+, -, *, /, //, %, ** 和一元 +/-"
        raise ToolInputError(
            f"不支持的运算 '{node_type}'。calculator 仅支持: {supported}。"
            f"问题片段: {ast.dump(node)}"
        )


def build_tools() -> list[Tool]:
    return build_tools_from_manifest(MANIFEST, CalculatorExecutor())
