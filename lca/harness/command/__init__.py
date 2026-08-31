"""Session spine command dispatcher.

ADR-0119 followup-2 (2026-08-31): 原模块 ``lca.harness.command.gateway``
改名为 ``lca.harness.command.dispatcher``。"Dispatcher" 是 ADR-0106 §4.1
命名宪法许可角色后缀。语义为 session spine (0090 / 0092) 的命令接收面。
"""

from lca.harness.command.dispatcher import SessionCommandCarrier

__all__ = ["SessionCommandCarrier"]
