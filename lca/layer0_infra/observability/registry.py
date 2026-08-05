"""导出器注册表 + 唯一构造入口（Strategy + Registry + Builder）。

- ``EXPORTER_FACTORIES``：名字 → 工厂；新增后端只加一行；
- ``create_observability``：外部唯一构造入口——解析 ``"console+langfuse"``
  之类的选择串，按 settings 装配 hub（处理器策略 + 导出器 + 桥）。
"""

from __future__ import annotations

from collections.abc import Callable

from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from lca.contracts.protocols import ObservabilityBackend
from lca.layer0_infra.observability.exporters.console import ConsoleNarratorExporter
from lca.layer0_infra.observability.exporters.jsonl import JsonlExporter
from lca.layer0_infra.observability.exporters.langfuse import LangfuseBridge
from lca.layer0_infra.observability.hub import ObservabilityHub
from lca.layer0_infra.observability.policy import AttributePolicy
from lca.layer0_infra.observability.settings import ObservabilitySettings

ExporterLike = SpanExporter | LangfuseBridge
ExporterFactory = Callable[[ObservabilitySettings], ExporterLike]

EXPORTER_NAME_CONSOLE = "console"
EXPORTER_NAME_JSONL = "jsonl"
EXPORTER_NAME_MEMORY = "memory"
EXPORTER_NAME_LANGFUSE = "langfuse"

EXPORTER_FACTORIES: dict[str, ExporterFactory] = {
    EXPORTER_NAME_CONSOLE: lambda _s: ConsoleNarratorExporter(),
    EXPORTER_NAME_JSONL: lambda s: JsonlExporter(s.jsonl_path),
    EXPORTER_NAME_MEMORY: lambda _s: InMemorySpanExporter(),
    EXPORTER_NAME_LANGFUSE: lambda s: LangfuseBridge(s),
}


class UnknownExporterError(ValueError):
    """请求了未注册的导出器名。"""

    def __init__(self, name: str) -> None:
        known = ", ".join(sorted(EXPORTER_FACTORIES))
        super().__init__(f"未知导出器 {name!r}；可用：{known}")


def create_observability(
    choice: str | ObservabilityBackend | None = None,
    *,
    settings: ObservabilitySettings | None = None,
) -> ObservabilityHub:
    """唯一构造入口：字符串选择 → 装配完成的 hub。

    - ``ObservabilityHub`` 实例：原样返回（已装配）；
    - ``None``：读 settings.backends（env ``LCA_OBS_BACKENDS``）；
    - ``"a+b"``：按 ``+``/``,`` 分隔解析导出器名。
    非 hub 的自定义 backend 实例不可作为选择传入（必须是完整 hub）。
    """
    if isinstance(choice, ObservabilityHub):
        return choice
    if isinstance(choice, ObservabilityBackend):
        raise TypeError(
            f"observability 实例必须是 ObservabilityHub（收到 {type(choice).__name__}）"
        )
    cfg = settings if settings is not None else ObservabilitySettings()
    names = _parse_choice(choice) if choice is not None else cfg.backend_names()
    exporters: list[SpanExporter] = []
    bridges: list[LangfuseBridge] = []
    for name in names:
        factory = EXPORTER_FACTORIES.get(name)
        if factory is None:
            raise UnknownExporterError(name)
        built = factory(cfg)
        if isinstance(built, LangfuseBridge):
            bridges.append(built)
        else:
            exporters.append(built)
    hub = ObservabilityHub(
        exporters,
        policy=AttributePolicy(cfg.verbosity, redact=cfg.redact_enabled),
        sampling_rate=cfg.sampling_rate,
    )
    for bridge in bridges:
        hub.attach_bridge(bridge)
    return hub


def _parse_choice(choice: str) -> list[str]:
    text = choice.replace(",", "+")
    return [part.strip() for part in text.split("+") if part.strip()]
