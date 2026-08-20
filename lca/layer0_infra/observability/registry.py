"""导出器/投影器注册表 + 唯一构造入口（Strategy + Registry + Builder）。

- ``EXPORTER_FACTORIES``：名字 → OTel 导出器工厂（span 平面后端）；
- ``JOURNAL_PROJECTOR_FACTORIES``：名字 → journal 投影器工厂（叙事平面后端，
  ADR-0037；console 人类视图由此驱动，而非 span）；
- ``create_observability``：外部唯一构造入口——解析 ``"console+langfuse"``
  之类的选择串，按 settings 装配 hub（处理器策略 + 导出器 + 投影器 + 桥）。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import structlog
from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from lca.contracts.protocols import DiagnosticSink, JournalProjector, ObservabilityBackend
from lca.layer0_infra.observability.exporters.langfuse import (
    ExporterUnavailableError,
    LangfuseBridge,
)
from lca.layer0_infra.observability.hub import ObservabilityHub
from lca.layer0_infra.observability.journal.console_projector import ConsoleJournalProjector
from lca.layer0_infra.observability.journal.jsonl_projector import JsonlJournalProjector
from lca.layer0_infra.observability.policy import AttributePolicy
from lca.layer0_infra.observability.settings import ObservabilitySettings

ExporterLike = SpanExporter | LangfuseBridge
ExporterFactory = Callable[[ObservabilitySettings], ExporterLike]
ProjectorFactory = Callable[[ObservabilitySettings], JournalProjector]

EXPORTER_NAME_CONSOLE = "console"
EXPORTER_NAME_JSONL = "jsonl"
EXPORTER_NAME_MEMORY = "memory"
EXPORTER_NAME_LANGFUSE = "langfuse"

EXPORTER_FACTORIES: dict[str, ExporterFactory] = {
    EXPORTER_NAME_MEMORY: lambda _s: InMemorySpanExporter(),
    EXPORTER_NAME_LANGFUSE: lambda s: LangfuseBridge(s),
}

JOURNAL_PROJECTOR_FACTORIES: dict[str, ProjectorFactory] = {
    EXPORTER_NAME_CONSOLE: lambda s: ConsoleJournalProjector(s.verbosity),
    EXPORTER_NAME_JSONL: lambda s: JsonlJournalProjector(s.jsonl_path),
}


class UnknownExporterError(ValueError):
    """请求了未注册的导出器名。"""

    def __init__(self, name: str) -> None:
        known = ", ".join(sorted({*EXPORTER_FACTORIES, *JOURNAL_PROJECTOR_FACTORIES}))
        super().__init__(f"未知导出器 {name!r}；可用：{known}")


def create_observability(
    choice: str | ObservabilityBackend | None = None,
    *,
    settings: ObservabilitySettings | None = None,
    extra_projectors: Sequence[JournalProjector] = (),
    diagnostic_sinks: Sequence[DiagnosticSink] = (),
) -> ObservabilityHub:
    """唯一构造入口：字符串选择 → 装配完成的 hub。

    - ``ObservabilityHub`` 实例：原样返回（已装配）；
    - ``None``：读 settings.backends（env ``LCA_OBS_BACKENDS``）；
    - ``"a+b"``：按 ``+``/``,`` 分隔解析后端名（console 走 journal 投影器，
      jsonl/memory/langfuse 走 OTel 导出器/桥）。
    - ``extra_projectors``：本次装配额外的 journal 读者（如 Run 的 LiveTail）。
      与 backends 投影器同序扇出，不是平行总线；
    - ``diagnostic_sinks``：run-scoped 非事实诊断读者（如 JSONL 文件），
      与 Journal 恢复/重放语义严格分离。
    非 hub 的自定义 backend 实例不可作为选择传入（必须是完整 hub）。
    Langfuse 不可用（未装 SDK / 无凭据）时跳过并记日志，不阻断其它读者。
    """
    if isinstance(choice, ObservabilityHub):
        if extra_projectors:
            raise TypeError("已装配的 ObservabilityHub 不能再接收 extra_projectors")
        return choice
    if isinstance(choice, ObservabilityBackend):
        raise TypeError(
            f"observability 实例必须是 ObservabilityHub（收到 {type(choice).__name__}）"
        )
    cfg = settings if settings is not None else ObservabilitySettings()
    names = _parse_choice(choice) if choice is not None else cfg.backend_names()
    exporters: list[SpanExporter] = []
    projectors: list[JournalProjector] = []
    bridges: list[LangfuseBridge] = []
    for name in names:
        projector_factory = JOURNAL_PROJECTOR_FACTORIES.get(name)
        if projector_factory is not None:
            projectors.append(projector_factory(cfg))
            continue
        exporter_factory = EXPORTER_FACTORIES.get(name)
        if exporter_factory is None:
            raise UnknownExporterError(name)
        try:
            built = exporter_factory(cfg)
        except ExporterUnavailableError:
            structlog.get_logger(__name__).warning(
                "observability_backend_unavailable",
                backend=name,
            )
            continue
        if isinstance(built, LangfuseBridge):
            bridges.append(built)
        else:
            exporters.append(built)
    hub = ObservabilityHub(
        exporters,
        policy=AttributePolicy(cfg.verbosity, redact=cfg.redact_enabled),
        sampling_rate=cfg.sampling_rate,
        environment=cfg.environment,
        journal_projectors=[*projectors, *extra_projectors],
        diagnostic_sinks=diagnostic_sinks,
    )
    for bridge in bridges:
        try:
            hub.attach_bridge(bridge)
        except ExporterUnavailableError:
            structlog.get_logger(__name__).warning(
                "observability_bridge_attach_failed",
                backend=type(bridge).__name__,
            )
    return hub


def _parse_choice(choice: str) -> list[str]:
    text = choice.replace(",", "+")
    return [part.strip() for part in text.split("+") if part.strip()]
