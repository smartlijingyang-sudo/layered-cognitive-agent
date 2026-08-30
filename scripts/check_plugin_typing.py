#!/usr/bin/env python3
"""Pre-commit hook: 插件 setup / build_ 工厂函数必须有完整类型标注。

第一性原理：
  - 装饰器 ``@plugin`` 的签名已经把 setup 的类型约束在了
    :data:`lca.harness.plugin_api.PluginSetupFn` 上，mypy 应该兜底。
  - 但 mypy 在某些环境（缺 stub、本地跳过、CI 缓存失效）下可能漏报；
    这个脚本是确定性兜底：AST 静态扫描，绕过 mypy 也跑不掉。
  - 同时覆盖「build_* 工厂函数」——这些函数不进装饰器签名，但
    注册到 ctx.register / ctx.provide 工厂位，回调时缺类型会传开 Any。

扫描规则：
  - ``async def setup(ctx, config)`` / ``def setup(ctx, config)``：
    ``ctx`` 与 ``config`` 都必须有标注（否则 no-untyped-def）。
  - 顶层或模块级的 ``def build_*(...)`` 工厂函数：所有位置参数必须有标注，
    返回必须有标注。
  - 已标注 ``# type: ignore[no-untyped-def]`` 的不豁免——逃生口一律关闭。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PLUGINS_ROOT = _ROOT / "lca" / "plugins"
_PLUGIN_API = _ROOT / "lca" / "harness" / "plugin_api.py"

# 装饰器识别：仅当函数被 ``@plugin``（来自 lca.harness.plugin_api）装饰时
# 才强制 setup 签名。这条规则只对 lca/plugins/ 下的代码生效，避免误伤
# gateway/ 或 tests/ 里偶然出现同名函数。
_PLUGIN_DECORATOR_NAMES = frozenset({"plugin"})


def _is_plugin_decorated(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in node.decorator_list:
        # @plugin
        if isinstance(dec, ast.Name) and dec.id in _PLUGIN_DECORATOR_NAMES:
            return True
        # @plugin(...)
        if isinstance(dec, ast.Call):
            func = dec.func
            if isinstance(func, ast.Name) and func.id in _PLUGIN_DECORATOR_NAMES:
                return True
    return False


def _missing_param_annotation(args: ast.arguments, *, require_config: bool) -> list[str]:
    """返回缺标注的参数名列表（按形参顺序）。"""
    missing: list[str] = []
    pos_args = list(args.posonlyargs) + list(args.args)
    for i, arg in enumerate(pos_args):
        if arg.annotation is None and (i == 0 or require_config):
            missing.append(arg.arg)
    return missing


def _missing_return_annotation(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return node.returns is None


def _has_docstring(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return (
        len(node.body) > 0
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, (ast.Constant, ast.JoinedStr))
    )


def _check_file(path: Path) -> list[str]:
    """返回违规条目列表；空 = 通过。"""
    rel = path.relative_to(_ROOT)
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        return [f"{rel}: parse failed: {exc}"]

    violations: list[str] = []

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # ── 规则 1：@plugin 装饰的 setup 函数 ────────────────────────────
        if node.name == "setup" and _is_plugin_decorated(node):
            missing = _missing_param_annotation(node.args, require_config=True)
            if missing:
                violations.append(
                    f"{rel}:{node.lineno}: @plugin setup() 缺参数类型标注: "
                    f"{', '.join(missing)} (期望 ctx: PluginContext, config: <BaseModel>)"
                )
            # 返回类型：Coroutine[Any, Any, None]，目前允许 -> None / -> Awaitable[None]
            # _wrap 已经要求返回 None（PluginSetupFn 定义），所以缺返回标注也算违规。
            if _missing_return_annotation(node):
                violations.append(f"{rel}:{node.lineno}: @plugin setup() 缺返回类型标注 (-> None)")

        # ── 规则 2：模块级 / 类外的 build_ 工厂函数 ────────────────────
        # build_ 函数名约定：注册到 ctx.register / ctx.provide 的工厂。
        # 必须有完整签名，否则调用方只能拿到 Callable[..., Any]。
        elif node.name.startswith("build_") and _is_module_level(tree, node):
            for arg in (
                list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)
            ):
                if arg.annotation is None and arg.arg != "self":
                    violations.append(
                        f"{rel}:{node.lineno}: build_ 工厂参数 '{arg.arg}' 缺类型标注"
                    )
            if _missing_return_annotation(node):
                violations.append(f"{rel}:{node.lineno}: build_ 工厂 '{node.name}' 缺返回类型标注")

    return violations


def _is_module_level(tree: ast.Module, node: ast.AST) -> bool:
    """函数是否定义在模块顶层（不在 class / 嵌套 def 里）。"""
    return any(child is node for child in tree.body)


def main() -> int:
    if not _PLUGINS_ROOT.is_dir():
        print(f"❌ 找不到插件目录: {_PLUGINS_ROOT}", file=sys.stderr)
        return 2

    files = sorted(_PLUGINS_ROOT.rglob("*.py"))
    all_violations: list[str] = []
    for path in files:
        all_violations.extend(_check_file(path))

    if all_violations:
        print("❌ 插件类型标注缺失：")
        print()
        for v in all_violations:
            print(f"  {v}")
        print()
        print(
            "修复：@plugin setup 的 ctx 标 PluginContext, config 标具体 Config;\n"
            "     build_xxx 工厂补全参数 + 返回标注。"
        )
        return 1

    print(f"✅ 插件类型标注检查通过 ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
