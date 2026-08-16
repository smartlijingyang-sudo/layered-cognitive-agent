"""llm 插件 —— 测试用。"""

from lca.contracts.mechanisms.plugin import PluginConfig

name = "llm"
inject: tuple[str, ...] = ()
provides = "llm"
Config = PluginConfig


def apply(ctx: object, config: object) -> None:
    pass
