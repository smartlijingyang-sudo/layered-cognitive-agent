"""YAML ``!py`` expression — Cordis ``!!js`` safe equivalent.

DSH uses ``!!js "ctx.env.API_KEY"`` raw eval in config files. This module
replaces that with an AST-whitelist sandbox: only safe constant / attribute
/ subscript / arithmetic / comparison / boolean / container operations and a
fixed builtin set are allowed. Config values are interpolated at load time
against the plugin's context.

Spec reference: ``docs/superpowers/specs/2026-08-16-plugin-tree-runtime-design.md`` §5.15.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from typing import Any

import yaml

_SAFE_NODES: tuple[type[ast.AST], ...] = (
    ast.Constant,
    ast.Name,
    ast.Attribute,
    ast.Subscript,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Set,
    ast.BoolOp,
    ast.Compare,
    ast.BinOp,
    ast.UnaryOp,
    ast.IfExp,
    ast.Call,
)

_SAFE_BUILTINS: dict[str, Any] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "len": len,
    "range": range,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    "sorted": sorted,
    "True": True,
    "False": False,
    "None": None,
}

_BIN_OPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.Not: operator.not_,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_CMP_OPS: dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


class PyExpr:
    """YAML ``!py`` tag value carrier.

    Serializable, diffable, and re-writable — the raw expression string is
    retained and only evaluated when ``SafeEvaluator.evaluate`` runs.
    """

    def __init__(self, expr: str) -> None:
        self.expr = expr

    def __repr__(self) -> str:
        return f"PyExpr({self.expr!r})"


class SafeEvaluator:
    """AST-whitelist sandbox. Supports the safe expression subset only.

    :param scope: variable namespace, e.g. ``{"ctx": plugin_context}``.
    """

    def __init__(self, scope: dict[str, Any] | None = None) -> None:
        self._scope = scope or {}

    def evaluate(self, expr: str) -> Any:
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"invalid !py expression: {expr!r}") from exc
        return self._eval(tree.body)

    def _eval(self, node: ast.AST) -> Any:
        if type(node) not in _SAFE_NODES:
            raise ValueError(f"unsafe AST node in !py: {type(node).__name__}")

        match node:
            case ast.Constant(value=value):
                return value
            case ast.Name(id=name):
                if name in self._scope:
                    return self._scope[name]
                if name in _SAFE_BUILTINS:
                    return _SAFE_BUILTINS[name]
                raise ValueError(f"undefined name in !py: {name!r}")
            case ast.Attribute(value=value, attr=attr):
                obj = self._eval(value)
                if isinstance(obj, dict) and attr in obj:
                    return obj[attr]
                return getattr(obj, attr)
            case ast.Subscript(value=value, slice=slice_node):
                obj = self._eval(value)
                if slice_node is None:
                    raise ValueError("subscript with empty slice is not supported")
                key = self._eval(slice_node)
                return obj[key]
            case ast.List(elts=elts):
                return [self._eval(e) for e in elts]
            case ast.Tuple(elts=elts):
                return tuple(self._eval(e) for e in elts)
            case ast.Dict(keys=keys, values=values):
                result: dict[Any, Any] = {}
                for k, v in zip(keys, values, strict=True):
                    if k is not None:
                        result[self._eval(k)] = self._eval(v)
                return result
            case ast.Set(elts=elts):
                return {self._eval(e) for e in elts}
            case ast.BoolOp(op=op, values=values):
                vals = [self._eval(v) for v in values]
                return all(vals) if isinstance(op, ast.And) else any(vals)
            case ast.Compare(left=left, ops=ops, comparators=comps):
                result = self._eval(left)
                for cmpop, right in zip(ops, comps, strict=True):
                    rv = self._eval(right)
                    cmp_fn = _CMP_OPS.get(type(cmpop))
                    if cmp_fn is None or not cmp_fn(result, rv):
                        return False
                    result = rv
                return True
            case ast.BinOp(left=left, op=op, right=right):
                return _BIN_OPS[type(op)](self._eval(left), self._eval(right))
            case ast.UnaryOp(op=op, operand=operand):
                return _UNARY_OPS[type(op)](self._eval(operand))
            case ast.IfExp(test=test, body=body, orelse=orelse):
                return self._eval(body) if self._eval(test) else self._eval(orelse)
            case ast.Call(func=func, args=args, keywords=keywords):
                fn = self._eval(func)
                if fn not in _SAFE_BUILTINS.values():
                    raise ValueError(f"unsafe call in !py: {ast.dump(func)}")
                pos = [self._eval(a) for a in args]
                kw = {kw.arg: self._eval(kw.value) for kw in keywords if kw.arg is not None}
                return fn(*pos, **kw)
            case _:
                raise ValueError(f"unsupported AST node in !py: {type(node).__name__}")


def _py_constructor(loader: yaml.SafeLoader, node: yaml.Node) -> PyExpr:
    value = loader.construct_scalar(node)
    return PyExpr(value)


yaml.SafeLoader.add_constructor("!py", _py_constructor)
yaml.SafeLoader.add_constructor("tag:yaml.org,2002:py", _py_constructor)
yaml.FullLoader.add_constructor("!py", _py_constructor)
yaml.FullLoader.add_constructor("tag:yaml.org,2002:py", _py_constructor)


def interpolate(value: Any, scope: dict[str, Any]) -> Any:
    """Recursively replace ``PyExpr`` nodes in *value*."""
    if isinstance(value, PyExpr):
        return SafeEvaluator(scope).evaluate(value.expr)
    if isinstance(value, dict):
        return {k: interpolate(v, scope) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate(v, scope) for v in value]
    if isinstance(value, tuple):
        return tuple(interpolate(v, scope) for v in value)
    return value
