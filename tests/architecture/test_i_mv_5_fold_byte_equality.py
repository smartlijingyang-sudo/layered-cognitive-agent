"""I-MV-5 架构不变量 —— ADR-0185 §4。

I-MV-5: ``lca_kernel/events/fold.py`` 必须是**纯函数模块**,无文件 I/O、
无 ContextVar 副作用、无全局状态变更。fold 优化依赖字节级判等
(``headerEquals``) 与 ``canonicalHeader`` 归一化,如果模块偷偷读写磁盘
或污染全局状态,journal 体积控制契约就会破。

守护方式:扫描 ``lca_kernel/events/fold.py`` 不出现 ``open(`` / ``Path(``
``read(`` / ``write(`` 调用(仅允许在 docstring 中以字面文字出现)。

对齐:deepseek-harness ``packages/core/session/src/request-header.ts`` 的
``foldRequestHeader`` 也是纯函数 —— 任何时候 import fold 模块都不应
触发副作用。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FOLD_MODULE = _REPO_ROOT / "lca_kernel" / "events" / "fold.py"


_FORBIDDEN_CALL_NAMES: frozenset[str] = frozenset({"open", "Path", "read", "write"})


class TestIMv5:
    """I-MV-5: fold 模块纯函数性。"""

    def test_fold_module_exists(self) -> None:
        if not _FOLD_MODULE.exists():
            pytest.skip("fold.py not found at lca_kernel/events/fold.py")
        assert _FOLD_MODULE.is_file()

    def test_fold_module_no_io_calls(self) -> None:
        """``fold.py`` AST 中不出现 ``open(`` / ``Path(`` / ``read(`` / ``write(`` 调用。

        仅检查 call/attribute 节点;docstring / 注释中的字面文字由 AST 隔离
        (docstring 是 Expr 节点,不是 Call,不会被命中)。
        """
        if not _FOLD_MODULE.exists():
            pytest.skip("fold.py not found")
        tree = ast.parse(_FOLD_MODULE.read_text(encoding="utf-8"), filename=str(_FOLD_MODULE))
        offenders: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            target: ast.AST | None = None
            if isinstance(node, ast.Call):
                func = node.func
                # 直接调用: open(...) / Path(...)
                if (isinstance(func, ast.Name) and func.id in _FORBIDDEN_CALL_NAMES) or (
                    isinstance(func, ast.Attribute) and func.attr in _FORBIDDEN_CALL_NAMES
                ):
                    target = func
            elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_CALL_NAMES:
                # 也扫裸属性引用(避免变量名 = open 这种诡异写法)
                # 但忽略赋值目标(bind 写法可能合法);仅当属性后跟 Call 才算
                # —— ast.Call 已覆盖,这里跳过裸属性
                continue
            if target is not None:
                offenders.append((node.lineno, ast.dump(target)))
        assert not offenders, (
            "I-MV-5 违规:fold.py 出现 I/O 调用,fold 模块必须是纯函数\n"
            + "\n".join(f"  line {lineno}: {dump}" for lineno, dump in offenders[:5])
        )

    def test_fold_module_no_mutable_global_state(self) -> None:
        """``fold.py`` 模块级不应有可变全局状态(``__all__`` + 不可变常量除外)。

        不可变常量(``str`` / ``int`` / ``frozenset`` / ``tuple`` 等)允许;
        ``dataclass`` 实例 / list / dict / set 出现在模块级就视为可变状态。
        """
        if not _FOLD_MODULE.exists():
            pytest.skip("fold.py not found")
        tree = ast.parse(_FOLD_MODULE.read_text(encoding="utf-8"), filename=str(_FOLD_MODULE))
        offenders: list[tuple[int, str]] = []
        # 仅在 Module 节点直接 children 里检查赋值,跳过函数体内赋值
        for node in tree.body:
            if isinstance(node, ast.Assign):
                # 允许 __all__ 赋值
                targets_repr = ast.dump(node.targets[0]) if node.targets else ""
                if "__all__" in targets_repr:
                    continue
                # 仅当值是 list / dict / set 字面量或 list/dict/set 构造时才视为可变
                if (
                    node.value
                    and isinstance(
                        node.value,
                        (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp),
                    )
                ) or (
                    node.value
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id in {"list", "dict", "set", "defaultdict", "OrderedDict"}
                ):
                    offenders.append((node.lineno, targets_repr))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id == "__all__":
                    continue
                # AnnAssign: 仅当 annotation 显式为 mutable 容器才视为可变状态
                if node.annotation is None:
                    continue
                ann_str = ast.unparse(node.annotation) if hasattr(ast, "unparse") else ""
                # frozenset 是不可变容器;先从字面里剔除,避免 "frozenset[" 误中 "set["
                ann_str = ann_str.replace("frozenset[", "")
                mutable_annotations = (
                    "list[",
                    "dict[",
                    "set[",
                    "List[",
                    "Dict[",
                    "Set[",
                    "MutableMapping",
                    "MutableSet",
                    "MutableSequence",
                )
                if any(prefix in ann_str for prefix in mutable_annotations):
                    offenders.append((node.lineno, node.target.id))
        assert not offenders, "I-MV-5 违规:fold.py 模块级有可变全局状态\n" + "\n".join(
            f"  line {lineno}: {t}" for lineno, t in offenders[:5]
        )
