"""Session spine command carrier.

历史命名: 此模块曾叫 "Command gateway" (module path
``lca.harness.command.gateway``),沿用至今。语义不是 ADR-0119 决定 4
之后的 ``kernel_serve`` LCA 后台进程,而是 session spine (0090 / 0092)
命令接收面。完整命名空间历史映射看
``docs/adr/0119-followup-gateway-name-map.md``。
"""

from lca.harness.command.gateway import SessionCommandCarrier

__all__ = ["SessionCommandCarrier"]