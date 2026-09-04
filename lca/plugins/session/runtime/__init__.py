"""Session runtime —— DSH 风格 Session 实体与 in-memory 仓库（PR-3c 骨架）。

- :class:`Session` —— append-only 日志真值 + observer contained fire +
  reentry 拒绝 + 增量 request_header fold
- :class:`SessionStore` —— create / get / dispose
- :class:`SessionBusFacade` —— Session → publisher/observer bus Protocol 适配

plugin 装配入口是 :mod:`lca.plugins.session.runtime.plugin`（``@plugin``
唯一入口，本 ``__init__`` 不声明 plugin）。
"""

from lca.plugins.session.runtime.bus_facade import SessionBusFacade
from lca.plugins.session.runtime.session import Session
from lca.plugins.session.runtime.store import SessionStore

__all__ = ["Session", "SessionBusFacade", "SessionStore"]
