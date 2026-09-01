"""Observability firewall —— 全链路桥接异常的唯一终结点。

设计动机
========

ADR-0164 引入的 bridge 层(``step_emitter`` / ``perceive_hub`` /
``tool_journal_emit`` / ``event_emission``)在认知主链路与 step_lifecycle /
journal / tracer 之间承担"翻译"职责。 翻译代码有两个固有问题:

1. **schema 漂移**:  桥接字段名 / 类型随两侧 contract 演进而错位
   (``state.objective`` vs ``state.task``, ``StepContext.objective``
   要求 ``str`` 但有时传 ``None``, 等等)。 错位 → :class:`AttributeError`
   或 :class:`TypeError` 沿调用栈冒泡, 直接打死主链路。
2. **异常屏蔽碎片化**: 历史上每个 bridge helper 自己写
   ``try/except (RuntimeError, ImportError): return None``。 这种
   "半吊子" 屏蔽会漏掉 :class:`AttributeError` / :class:`KeyError`
   / :class:`ValueError` 等常见 schema 错误 —— 一次真实故障的根因。

第一性原则(per AGENTS.md "工程思维:追问前提")
==================================================

> 不要在错误机制上堆补丁。 遇到长 if/else, 先考虑 Registry / Strategy /
> Provider; 遇到重复逻辑, 检查抽象层; 遇到 workaround、死监听或深调用链,
> 检查是否应删除、正式接入或重新划分职责。

按此原则, 本模块**不修改任何既有调用方代码**, 而是提供一个唯一
``bridge_firewall`` contextmanager: **任何** :class:`BaseException` 进入
都被立即捕获、就地写入 :class:`RuntimeObserved`, 然后 swallow。 之后
所有 ``step_emitter._safe_*`` / 任何用户桥接代码都改成 ``with
bridge_firewall(...):`` 一行即可, 不再需要各自写 try/except。

可观测性
=========

每次 firewall 触发一条 :class:`RuntimeObserved`:

    category = PLUGIN
    operation = "bridge.<caller_supplied>"
    attributes = {error_type, error_message, ...caller_attrs}
    status = FAILED

这条事件立刻经 facade 写到 journal; ``lca-ops debug-run <run_id>`` /
``journal steps`` 可以直接 grep ``operation == "bridge.<name>"`` 拿到
完整 traceback 的入口信号。 firewall 自身再次失败 → 仅 structlog warning,
绝不反向 throw 把链路打死。

显式约定
========

- :class:`KeyboardInterrupt` / :class:`SystemExit` **永远向上抛** —— 用户
  主动中断和 Python 解释器信号不能被桥接层吞掉。
- firewall contextmanager 的 return type 是 ``Iterator[None]``: 调用方
  不在 ``with`` 块里 return 业务值, 而是在外层维护变量再 yield 出来。
  这是与 :class:`contextlib.suppress` / :class:`nullcontext` 一致的形态。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog

from lca.contracts.models.observability.diagnostic import DiagnosticCategory, DiagnosticStatus

_log = structlog.get_logger("lca.observability.firewall")

# 不被 firewall 吞掉的异常 — 显式收口, 而不是用 ``BaseException`` 通配
_UNCATCHABLE: tuple[type[BaseException], ...] = (KeyboardInterrupt, SystemExit)


def record_bridge_failure(
    *,
    operation: str,
    error_type: str,
    error_message: str,
    attributes: dict[str, Any] | None = None,
) -> None:
    """把一次桥接异常作为 :class:`RuntimeObserved` 写入 journal。

    facade / record_runtime 自身抛 → 兜底 structlog, 绝不让 firewall
    反向 throw 把链路打死。
    """
    try:
        from lca.infrastructure.observability import record_runtime

        record_runtime(
            DiagnosticCategory.PLUGIN,
            operation,
            plugin="observability_firewall",
            attributes={
                "error_type": error_type,
                "error_message": error_message,
                **(attributes or {}),
            },
            output={"swallowed": True},
            status=DiagnosticStatus.FAILED,
        )
    except BaseException:  # firewall 必须 self-resilient
        _log.warning(
            "bridge_firewall_self_failed",
            operation=operation,
            error_type=error_type,
        )


@contextmanager
def bridge_firewall(
    operation: str,
    *,
    attributes: dict[str, Any] | None = None,
    propagate: tuple[type[BaseException], ...] = _UNCATCHABLE,
) -> Iterator[None]:
    """隔离桥接层异常 —— 全链路统一的异常终结点。

    使用::

        with bridge_firewall("bridge.perceive_opened", phase="perceive"):
            ...  # 任意代码; 任何 Exception 都被捕获 + 写入 journal

    Parameters
    ----------
    operation:
        写进 journal ``operation`` 字段, 例如 ``"bridge.perceive_opened"``。
        按 ``bridge.<caller>`` 命名空间划分, 便于 debug-run 过滤。
    attributes:
        额外属性(phase / step / tool_name / actor 等), 全部进入
        ``RuntimeObserved.attributes``, 用于现场定位。
    propagate:
        不被吞的异常类型元组。 默认不吞 :class:`KeyboardInterrupt` /
        :class:`SystemExit`; 测试可在局部覆盖。
    """
    try:
        yield
    except propagate:
        raise
    except BaseException as exc:  # 显式吞掉一切可恢复异常
        # 二次防护: record_bridge_failure 自身被 monkey-patch / record 通道整体
        # 挂掉时,绝不能让异常反向冒出 firewall —— firewall 自身必须是最后
        # 一道兜底。 structlog 在最坏情况下仍可工作。
        try:
            record_bridge_failure(
                operation=operation,
                error_type=type(exc).__name__,
                error_message=str(exc)[:500],
                attributes=attributes,
            )
        except BaseException as record_exc:  # firewall 的 firewall
            _log.warning(
                "bridge_firewall_double_failure",
                operation=operation,
                original_error_type=type(exc).__name__,
                record_error_type=type(record_exc).__name__,
            )


__all__ = ["bridge_firewall", "record_bridge_failure"]
