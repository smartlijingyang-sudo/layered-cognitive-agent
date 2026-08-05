"""Langfuse 桥接 —— 把 Langfuse SDK（OTel 原生）挂进 hub 的 TracerProvider。

适配器模式：LCA span 树 → Langfuse trace/session/generation/event。
- 根 span → trace（session.id 映射会话视图）；
- llm.chat → generation（gen_ai.* 语义约定 → model/tokens/cost 自动核算）；
- OTel span event → Langfuse event。

SDK 懒加载：构造期校验依赖与凭据；``attach`` 期才创建客户端并挂接
provider（hub 先于 bridge 存在）。未安装 ``langfuse`` 可选组时抛
``ExporterUnavailableError``，不影响框架其余部分运行。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from lca.contracts.protocols import ObservabilityBackend
from lca.layer0_infra.observability.settings import ObservabilitySettings

if TYPE_CHECKING:
    from lca.layer0_infra.observability.hub import ObservabilityHub

_log = structlog.get_logger("lca.observability.langfuse")

_INSTALL_HINT = "uv sync --group observability-langfuse"


class ExporterUnavailableError(Exception):
    """导出器不可用（依赖缺失或凭据未配置）。"""


class LangfuseBridge(ObservabilityBackend):
    """Langfuse 后端桥接：构造期校验，``attach`` 期挂接 provider。"""

    def __init__(self, settings: ObservabilitySettings) -> None:
        try:
            import langfuse  # noqa: F401
        except ImportError as exc:
            raise ExporterUnavailableError(
                f"langfuse SDK 未安装，请先执行：{_INSTALL_HINT}"
            ) from exc
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            raise ExporterUnavailableError(
                "Langfuse 凭据未配置（LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY）"
            )
        self._public_key = settings.langfuse_public_key
        self._secret_key = settings.langfuse_secret_key
        self._host = settings.langfuse_host
        self._client: Any = None

    def attach(self, hub: ObservabilityHub) -> None:
        """创建 Langfuse 客户端并挂到 hub 的 TracerProvider。"""
        from langfuse import Langfuse

        self._client = Langfuse(
            public_key=self._public_key,
            secret_key=self._secret_key,
            host=self._host,
            tracer_provider=hub.provider,
            # LCA span 全部导出（SDK 默认过滤器只收 gen_ai/SDK span）
            should_export_span=lambda _span: True,
        )
        hub.register_scorer(self._score_current)

    def _score_current(self, name: str, value: float, attributes: dict[str, Any]) -> None:
        if self._client is None:
            raise ExporterUnavailableError("Langfuse 客户端未挂接（attach 之前不可评分）")
        self._client.score_current_span(name=name, value=value, data=attributes or None)

    def flush(self) -> None:
        if self._client is not None:
            try:
                self._client.flush()
            except Exception:
                _log.warning("langfuse_flush_failed")

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.shutdown()
            except Exception:
                _log.warning("langfuse_shutdown_failed")
            self._client = None
