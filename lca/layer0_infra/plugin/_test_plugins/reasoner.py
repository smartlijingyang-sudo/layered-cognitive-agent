"""reasoner 插件 —— 测试用。"""

from lca.contracts.mechanisms.plugin import PluginConfig

name = "reasoner"
inject = ("llm",)
provides = "reasoner"
Config = PluginConfig


def apply(ctx: object, config: object) -> None:
    pass
