"""Profile 启动输入的可执行声明投影。

该模块把已解析插件声明收成公共启动序列消费的窄接口。启动生命周期只消费
``BootEntry``；检查视图由同一份 ``ResolvedProfile`` 派生，不再写入平行的
Context 动态属性。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from lca.harness.plugin_api import PluginDefinition

if TYPE_CHECKING:
    from lca.harness.profile.resolve import ResolvedProfile


@dataclass(frozen=True, slots=True)
class BootEntry:
    """一个由公共启动序列消费的已准备插件声明。"""

    id: str
    definition: PluginDefinition
    config: Any
    module: str | None

    @classmethod
    def from_resolved(cls, resolved: ResolvedProfile) -> tuple[BootEntry, ...]:
        """只启动未禁用的已解析插件，保持 Resolve 给出的拓扑顺序。"""

        return tuple(
            cls(
                id=item.id,
                definition=item.definition,
                config=item.config,
                module=item.module,
            )
            for item in resolved.plugins
            if not item.disabled
        )


__all__ = ["BootEntry"]
