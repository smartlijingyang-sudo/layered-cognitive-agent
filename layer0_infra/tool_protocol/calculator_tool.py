"""安全求值四则运算表达式工具（AST 白名单，杜绝任意代码执行）。"""

from __future__ import annotations

import ast
import operator
import time
import uuid
from typing import Any

from contracts.decision import Observation
from contracts.protocols import ToolProtocol


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class CalculatorTool(ToolProtocol):
    """实现 ToolProtocol 的示例工具。"""

    name = "calculator"
    is_idempotent = True
    default_timeout_s = 5

    _OPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.USub: operator.neg,
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        expr = args.get("expression", "")
        try:
            value = self._safe_eval(expr)
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=_new_id("obs"), success=True, payload=value, latency_ms=latency_ms
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=_new_id("obs"), success=False, payload=None,
                error=str(e), latency_ms=latency_ms,
            )

    def _safe_eval(self, expr: str) -> float:
        node = ast.parse(expr, mode="eval").body
        return self._eval_node(node)

    def _eval_node(self, node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in self._OPS:
            return self._OPS[type(node.op)](self._eval_node(node.left), self._eval_node(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in self._OPS:
            return self._OPS[type(node.op)](self._eval_node(node.operand))
        raise ValueError(f"不支持的表达式片段: {ast.dump(node)}")
