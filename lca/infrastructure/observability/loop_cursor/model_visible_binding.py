"""LLM 边界的 ``ModelVisibleCapture`` ContextVar 注入(ADR-0169 PR-12.5)。

职责
----
- 在 ``RunSessionBuilder.build`` 阶段与 ``install_run_cursor`` 配套注入,
  让 :class:`ModelVisibleLLMAdapter` 在 LLM 调用时通过
  ``get_current_model_visible_capture()`` 拿到 capture 实例。
- ContextVar 隔离多 run;reset token 由 caller 在 close 时释放。
- 不持任何真值(ADR-0169 G15 控制/观察分离);capture 写入 model_visible
  是它自己的事,本模块只做注入。

``install_model_visible_capture`` 一般与 ``install_run_cursor`` 成对:

.. code-block:: python

    cursor_token = install_run_cursor(cursor)
    capture_token = install_model_visible_capture(
        StdModelVisibleCapture(run_dir=run_dir)
    )
    try:
        ...
    finally:
        reset_model_visible_capture(capture_token)
        reset_run_cursor(cursor_token)
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

from lca.contracts.observability.model_visible_capture import ModelVisibleCapture

_current_capture: ContextVar[ModelVisibleCapture | None] = ContextVar(
    "lca_model_visible_capture_current", default=None
)


def get_current_model_visible_capture() -> ModelVisibleCapture | None:
    """取当前 run 绑定的 :class:`ModelVisibleCapture`;无则返回 ``None``。

    Adapter 在没有 capture 时**不**抛异常,而是走「透明透传」分支(
    不写盘、不落 spine EP,业务调用继续)—— 这是 ADR-0169 D5 / L10
    「capture 失败 / 缺席不挡业务」的硬要求。
    """
    return _current_capture.get()


def bind_current_capture(capture: ModelVisibleCapture) -> Token[Any]:
    """绑定 capture;返回 reset token。

    由 :class:`RunSessionBuilder` 在 :func:`install_run_cursor` 之后调;
    close 时由 caller 释放。
    """
    return _current_capture.set(capture)


def reset_current_capture(token: Token[Any]) -> None:
    _current_capture.reset(token)


# ── thin re-exports(loop_cursor 默认导出面对外)─────────────────


def install_model_visible_capture(capture: ModelVisibleCapture) -> Token[Any]:
    """注入 capture;返回 reset token。

    thin re-export,组合根只 import 一个符号。
    """
    return bind_current_capture(capture)


def reset_model_visible_capture(token: Token[Any]) -> None:
    """释放 ``install_model_visible_capture`` 返回的 token。"""
    reset_current_capture(token)


__all__ = [
    "bind_current_capture",
    "get_current_model_visible_capture",
    "install_model_visible_capture",
    "reset_current_capture",
    "reset_model_visible_capture",
]
