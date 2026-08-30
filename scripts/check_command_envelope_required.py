#!/usr/bin/env python3
"""check_command_envelope_required —— ADR-0068 §五 + ADR-0074 PR-7 V4 hard constraint。

扫描 ``lca/cognition/body/pipeline_safe_executor.py`` + 其他 body /
plugin body 文件,确保所有 ``execute()`` 调用栈必含 ``mint_envelope()`` 引用
(architecture test gate)。

acceptance §3.4 V4:

> AST 扫描 ``lca/cognition/body/`` + ``lca/plugins/body/`` 所有
> ``pipeline_safe_executor.execute`` 调用栈必含 ``command_envelope.mint``
> 引用。
> Body.execute 任意一次调用 stack trace 含 ``command_envelope.mint``。
> 缺 mint 的代码路径 exit 非 0 并打印违规文件:行号。

PR-7 阶段：

- 扫描 ``PipelineSafeExecutor.execute`` 方法体
- 验证 ``mint_envelope`` 或 ``command_envelope.mint`` 引用在方法体内
- 缺 mint 引用 → exit 1 + 打印违规文件:行号
- 后续 PR-7 后段 / PR-8 接入 5 闸完整 pipeline;本测试守住
  "execute 必经 mint_envelope" 这一最小约束

设计说明：

- 静态 AST 扫描（不执行 runtime；零副作用）
- 仅扫描 ``lca/cognition/body/`` + ``lca/plugins/body/``（body layer）
- 接受 ``mint_envelope(...)`` / ``command_envelope.mint(...)`` / ``command_envelope.mint_envelope(...)`` 3 种引用形式
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

SCAN_PATHS: tuple[Path, ...] = (
    REPO / "lca" / "cognition" / "body",
    REPO / "lca" / "plugins" / "body",
)

# 在 execute() 方法体内允许的 mint 引用形式
ALLOWED_MINT_FORMS: tuple[str, ...] = (
    "mint_envelope",
    "command_envelope.mint",
    "command_envelope.mint_envelope",
)


def _has_mint_reference(method_body: ast.AST) -> bool:
    """检查 method_body 内是否有 mint_envelope / command_envelope.mint 引用。"""
    for node in ast.walk(method_body):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in ALLOWED_MINT_FORMS:
            return True
        if isinstance(func, ast.Attribute):
            # command_envelope.mint(...) / command_envelope.mint_envelope(...)
            attr_chain: list[str] = []
            cur: ast.AST = func
            while isinstance(cur, ast.Attribute):
                attr_chain.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                attr_chain.append(cur.id)
            chain_str = ".".join(reversed(attr_chain))
            if chain_str in ALLOWED_MINT_FORMS:
                return True
            # 也接受任何 mint_envelope 调用（含 attribute form）
            if "mint_envelope" in attr_chain:
                return True
            if "command_envelope" in attr_chain and "mint" in attr_chain:
                return True
    return False


def _is_pipeline_executor_class(node: ast.ClassDef) -> bool:
    """是否为 PipelineSafeExecutor 类（或其他需要 mint 的 executor）。"""
    return node.name in {"PipelineSafeExecutor", "SafeExecutor"}


def _scan_file(path: Path) -> list[tuple[Path, int, str]]:
    violations: list[tuple[Path, int, str]] = []
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return violations
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not _is_pipeline_executor_class(node):
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if item.name != "execute":
                continue
            if not _has_mint_reference(item):
                violations.append(
                    (
                        path,
                        item.lineno,
                        f"{node.name}.{item.name}() lacks mint_envelope call "
                        f"(V4 acceptance: stack trace must contain mint_envelope)",
                    )
                )
    return violations


def main() -> int:
    violations: list[tuple[Path, int, str]] = []
    for scan_root in SCAN_PATHS:
        if not scan_root.exists():
            continue
        files: list[Path] = list(scan_root.rglob("*.py")) if scan_root.is_dir() else [scan_root]
        for f in files:
            violations.extend(_scan_file(f))

    if violations:
        for path, line_no, label in violations:
            print(f"VIOLATION {path}:{line_no}: {label}")
        print(
            f"\nV4 acceptance (PR-7): {len(violations)} execute() methods "
            f"lack mint_envelope call. Add "
            f"`from lca.contracts.protocols.command_envelope import mint_envelope` "
            f"and call mint_envelope(...) in body.execute()."
        )
        return 1

    print("OK: all execute() methods include mint_envelope call")
    return 0


if __name__ == "__main__":
    sys.exit(main())
