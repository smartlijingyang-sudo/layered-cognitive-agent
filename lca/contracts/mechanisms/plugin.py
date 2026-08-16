"""Plugin Protocol — 插件形状。

对齐 DSH Cordis：模块必须导出 ``name`` / ``inject`` / ``apply``。
本模块只定义形状；Loader 负责读模块属性。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class PluginConfig(BaseModel):
    """插件配置基类：默认空、未知字段拒绝。子类加字段；Loader 用其校验 YAML config。"""

    model_config = {"extra": "forbid"}


@runtime_checkable
class Plugin(Protocol):
    """插件形状。所有字段都是模块级导出，不是实例方法。

    显式继承本 Protocol 的检查由 ``check_protocol_impl.py`` 覆盖；
    这里只用作形状文档与类型约束。
    """

    name: str
    """插件稳定 id，在 profile YAML 中可被引用。"""

    inject: tuple[str, ...]
    """启动前必须已经 mount 的服务键。空 tuple 表示无依赖。"""

    provides: str | None
    """本插件 mount 的服务键；None 表示只往已有服务上注册。"""

    Config: type[PluginConfig]
    """校验后的配置模型类。Loader 在 apply 前用其 parse YAML config。"""

    def apply(self, ctx: Any, config: PluginConfig) -> None: ...
