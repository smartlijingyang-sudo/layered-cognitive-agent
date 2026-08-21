"""穷尽 match 工具 —— 事件处理的编译期完备性保证。

Python 没有 TypeScript 的声明合并和 ``assertNever``，可以用
穷尽检查。Python 没有 TypeScript 的声明合并和 ``assertNever``，但可以用
``match`` + ``assert_never`` 达到类似效果：

    from lca.contracts.atoms.exhaustive import assert_never

    match event_type:
        case "TeamRunStarted": ...
        case "TeamRunFinished": ...
        case _:
            assert_never(event_type)  # mypy 检测到未覆盖的 case 时报错

新增事件类型时，所有使用 ``assert_never`` 的 match 语句都会在类型检查时
报错——除非显式添加新 case，否则无法通过 mypy。

与 journal_catalog 的 ``JOURNAL_EVENT_CLASSES`` 配合使用：
词表登记 = 类型层面必须覆盖的 case 集合。
"""

from __future__ import annotations

from typing import NoReturn


def assert_never(value: NoReturn) -> NoReturn:
    """穷尽性检查：如果到达此处，说明 match 语句未覆盖所有 case。

    用法：在 match 的 ``case _:`` 分支调用。mypy 会在有遗漏时
    报类型错误（因为 ``value`` 的类型不是 ``NoReturn``）。

    """
    raise AssertionError(f"未覆盖的事件类型: {value!r}")
