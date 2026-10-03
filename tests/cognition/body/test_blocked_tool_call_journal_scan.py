from __future__ import annotations

# ADR-0282 T2: AST 级"新增闸门扫描"。
#
# 契约 (C1/C4): UseToolOperation.execute() 内,凡是返回一个 *_block_observation
# 产物的 return 点,其返回值必须是 _journal_blocked_call(...) 的调用。
# ADR 原文写的是 `return *_block_observation(...)` 内联形态;实现用的是
# "先赋值给变量,再 return _journal_blocked_call(decision, var)"形态——
# 本扫描两种都覆盖。
#
# 目的:新增一条派发前拒绝路径却绕开 _journal_blocked_call、或重构时删掉
# 某条闸门的包装,都会让本测试变红,逼修改者显式更新契约测试,而不是
# 静默丢弃"拒绝也要写实"。
#
# 扫描语义(全部在 AST 上,不执行生产代码):
# 1. 按语句顺序收集 `x = <gate>_block_observation(...)`(gate 判定:被调函数名
#    以 _block_observation 结尾);x 之后被重赋为非 gate 产物时移出集合。
# 2. 每个 return:若返回值引用了 gate 变量、或内联含 *_block_observation 调用,
#    则要求返回值本身就是 _journal_blocked_call(...) 调用,且被引用的 gate
#    变量/内联 gate 调用落在该调用的参数子树里(防"包了但包的不是这个 block")。
# 3. 另钉:ADR-0282 §1.1 断言的三条闸门必须仍在 execute 内被调用,且每条都有
#    至少一条经 _journal_blocked_call 的返回路径(防静默删闸门/改名——改了就
#    必须同步更新本测试,这是故意的显式动作要求)。
#
# 非目标:正常派发路径的 `return observations` 不引用 gate 产物,扫描天然放过;
# raise 不是 return,不在范围(ADR-0282 C5 边界声明)。
import ast
import inspect
from pathlib import Path

import lca.cognition.body.actions.action_handlers as handlers_mod

_GATE_SUFFIX = "_block_observation"
_JOURNAL_FN = "_journal_blocked_call"

# ADR-0282 §1.1 的三条闸门:删/改名任一条必须同步更新本测试。
_KNOWN_GATES = frozenset(
    {
        "tool_wire_block_observation",
        "unexposed_tool_block_observation",
        "missing_arguments_block_observation",
    }
)


def _call_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_gate_call(call: ast.Call) -> str | None:
    name = _call_name(call)
    if name and name.endswith(_GATE_SUFFIX):
        return name
    return None


def _iter_stmts(stmts):
    """Yield every statement, descending into compound bodies (if/try/...) but
    never into nested function/class/lambda scopes."""
    for stmt in stmts:
        yield stmt
        for child in ast.iter_child_nodes(stmt):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            if isinstance(child, (ast.stmt, ast.excepthandler)):
                yield from _iter_stmts([child])


def _execute_fn():
    path = inspect.getsourcefile(handlers_mod)
    assert path, "cannot locate action_handlers.py source"
    text = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(text)
    cls = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "UseToolOperation"
        ),
        None,
    )
    assert cls is not None, "UseToolOperation not found in action_handlers.py"
    fn = next(
        (
            node
            for node in cls.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "execute"
        ),
        None,
    )
    assert fn is not None, "UseToolOperation.execute not found"
    return text, fn


def _scan():
    """Return (violations, gate_funcs, journaled_gates)."""
    text, fn = _execute_fn()

    gate_vars: dict[str, str] = {}  # var name -> gate func name
    gate_funcs: set[str] = set()
    journaled_gates: set[str] = set()
    violations: list[str] = []

    for stmt in _iter_stmts(fn.body):
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            gate = _is_gate_call(stmt.value) if isinstance(stmt.value, ast.Call) else None
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                if gate:
                    gate_vars[target.id] = gate
                    gate_funcs.add(gate)
                else:
                    # Reassigned to a non-gate product: stop tracking it so a
                    # later return of the new value is not misjudged.
                    gate_vars.pop(target.id, None)
        elif isinstance(stmt, ast.Return) and stmt.value is not None:
            names = {n.id for n in ast.walk(stmt.value) if isinstance(n, ast.Name)}
            inline: set[str] = set()
            for call in ast.walk(stmt.value):
                if isinstance(call, ast.Call):
                    gate = _is_gate_call(call)
                    if gate:
                        inline.add(gate)
            ref_vars = names & gate_vars.keys()
            if not ref_vars and not inline:
                continue  # normal dispatch-path return, e.g. `return observations`
            value = stmt.value
            names_in_value = {n.id for n in ast.walk(value) if isinstance(n, ast.Name)}
            journaled = (
                isinstance(value, ast.Call)
                and _call_name(value) == _JOURNAL_FN
                and ref_vars <= names_in_value
                and all(
                    any(
                        isinstance(sub, ast.Call) and _call_name(sub) == gate
                        for sub in ast.walk(value)
                    )
                    for gate in inline
                )
            )
            if journaled:
                journaled_gates.update(gate_vars[var] for var in ref_vars)
                journaled_gates.update(inline)
            else:
                segment = ast.get_source_segment(text, stmt) or "<unavailable>"
                violations.append(f"line {stmt.lineno}: {segment.strip()}")
    return violations, gate_funcs, journaled_gates


def test_known_gates_still_wired_in_execute():
    """ADR-0282 §1.1 的三条闸门必须仍在 execute 内被调用。

    删掉一条闸门、或把它改名到不再以 _block_observation 结尾,都会红——
    这是故意的:改动者必须同步更新本契约测试,而不是静默丢弃。
    """
    _, gate_funcs, _ = _scan()
    missing = _KNOWN_GATES - gate_funcs
    assert not missing, (
        "gates no longer called in UseToolOperation.execute: "
        f"{sorted(missing)} (renamed or silently dropped — "
        "update this contract test deliberately)"
    )


def test_every_gate_return_goes_through_journal_blocked_call():
    """ADR-0282 C1/C4:派发前拒绝的返回点必须经 _journal_blocked_call。

    扫描 execute() 内所有 return:凡返回值引用 gate 变量或内联 gate 调用,
    必须是以 _journal_blocked_call(...) 包裹返回。新增闸门绕开它、或重构
    删掉某条闸门的包装,都会在这里红。
    """
    violations, _, journaled_gates = _scan()
    assert not violations, (
        "pre-dispatch refusal returned without _journal_blocked_call "
        "(ADR-0282 C1/C4):\n" + "\n".join(violations)
    )
    missing = _KNOWN_GATES - journaled_gates
    assert not missing, (
        "gates without a _journal_blocked_call return path in "
        f"UseToolOperation.execute: {sorted(missing)}"
    )
