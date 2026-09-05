"""Session 域辅助模块。

Session 真值层（append / observer / fold / 持久化）已迁至
``lca.plugins.session``（ADR-0186）；本目录保留跨平面共享的纯工具：

- ``emit`` —— typed session 事件对象 → ``Session.append`` 的统一发射出口。
"""

from lca.harness.session.emit import emit

__all__ = ["emit"]
