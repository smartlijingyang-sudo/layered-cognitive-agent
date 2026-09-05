"""Session 标题服务 plugin(ADR-0188,DSH session-title 一比一对位)。

plugin 装配入口是 :mod:`lca.plugins.session.title_service.title_service`
(``@plugin`` 唯一入口,本 ``__init__`` 不声明 plugin)。
"""

from lca.plugins.session.title_service.title_service import (
    Config,
    SessionTitleProvider,
    SessionTitleService,
    TitleUserMessage,
    normalize_title,
)

__all__ = [
    "Config",
    "SessionTitleProvider",
    "SessionTitleService",
    "TitleUserMessage",
    "normalize_title",
]
