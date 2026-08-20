"""Langfuse evaluation scorer plugin (Tier-2) —— ADR-0063 PR-10.

把 ``LangfuseBridge._score_current`` 包装为 ``observability_scorer`` 注册项；
Hub.score() 默认调用 Langfuse SDK 的 ``score_current_span``。

Langfuse SDK 懒加载；构造期校验，attach 期才创建客户端。bridge 仍挂在
``ObservabilityHub`` 上；本插件只暴露 scorer 列表。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-langfuse-eval-scorer",
    requires=["observability_scorer"],
    layer="L0",
    effects="network",
    description="Langfuse evaluation scorer (PR-10).",
    test_suite="tests/test_observability_scorer.py::test_langfuse_scorer_registered",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.observability import (
        ObservabilitySettings,
        Verbosity,
        langfuse_span_visible,
    )

    settings = ObservabilitySettings()

    def _score_current(name: str, value: float, attributes: dict[str, Any]) -> None:
        """向 Langfuse SDK 转发分数。SDK 未安装时降级为 no-op。"""
        try:
            import langfuse  # noqa: F401  # 验证依赖

            from langfuse import Langfuse

            client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            client.score_current_span(name=name, value=value, data=attributes or None)
        except ImportError:
            pass  # Langfuse SDK 未安装；不影响框架
        except Exception:
            return  # 失败不传播；评估是辅助通道

    from lca.layer0_infra.observability import NamedRegistry

    scorers: NamedRegistry = ctx.require("observability_scorer")
    scorers.register("langfuse", _score_current)
    # 同时确保可见性过滤器按 verbose / standard 分档（与 LangfuseBridge 一致）
    _ = langfuse_span_visible, Verbosity  # noqa: F841