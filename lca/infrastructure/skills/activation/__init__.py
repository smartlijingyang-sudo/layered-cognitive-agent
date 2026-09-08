"""Auto-created by split_oversized_directories.

PR-E 公开 bridge 入口供 ``runtime_loop`` 安装 + ``scope.register_activated``
转发使用。运行启动 install,运行结束 dispose。
"""

from __future__ import annotations

from lca.infrastructure.skills.activation.bridge import (
    SkillActivationReducerBridge,
    bridge,
)

__all__ = ["SkillActivationReducerBridge", "bridge"]
