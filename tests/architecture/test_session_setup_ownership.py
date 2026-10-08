from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_TRANSPORT_SESSION = (
    ROOT / "lca" / "plugins" / "transport" / "webserver" / "handlers" / "runs" / "session"
)


def _observability_from_imports(path: Path) -> dict[str, list[str]]:
    """Module -> imported names, for import statements mentioning observability."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "observability" in node.module:
            result.setdefault(node.module, []).extend(
                alias.asname or alias.name for alias in node.names
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if "observability" in alias.name:
                    result.setdefault(alias.name, []).append(alias.asname or alias.name)
    return result


def test_session_setup_coordinator_does_not_own_builder_or_diagnostics() -> None:
    """The setup facade coordinates distinct ownership modules."""
    setup = _TRANSPORT_SESSION / "setup" / "setup.py"
    source = setup.read_text(encoding="utf-8")

    assert "RunSessionBuilder" in source
    assert "RunBootSnapshotRecorder" in source
    assert "record_runtime" not in source
    assert "create_run_components" not in source


# todo-89 (arch 03:09 裁决取 (a) 修 pin): builder 的 observability 导入全部为组装
# 用途 —— 与 build() docstring ("Own identity allocation, carrier normalization,
# and run-local assembly" / "without publishing it to the registry") 及
# ADR-0167 D11 / ADR-0186 PR-3g (builder 阶段构造 StepCoordinator + 装配 per-run
# StepTreeFoldDeriver) 一致 —— 组装是 builder 的设计职责, 不是职责越界。
# pin 允许下述组装导入白名单, 但仍钉死"不向 registry 发布 (registry.put)、
# 不写 observability 数据 (record_runtime)"的负断言。
# 例外注记: emit_run_attachments (builder/builder.py:288-298, 来自 lifecycle_emit)
# 是容忍的 build-time journal 初始化 —— 请求附件的 journal 初始化 (空附件早退 +
# MissingCapabilityError 透过), 非 registry 发布 —— pin 刻意不禁它。
# 注: writable_matrix 的 5 面组件 (coalescer/serializer/storage/driver/emitter)
# 全部为装入 WritableFaceRegistry 的组装件, 一并列入白名单。
_ASSEMBLY_OBSERVABILITY_MODULES = frozenset(
    {
        "lca.contracts.observability.canonical_digest",
        "lca.contracts.observability.journal.run_journal",
        "lca.infrastructure.observability.loop_cursor.cursor_record",
        "lca.infrastructure.observability.loop_cursor.persistence.coordinator",
        "lca.infrastructure.observability.writable_matrix",
        "lca.infrastructure.observability.writable_matrix.registry",
        "lca.plugins.observability.run.ledger_seam",
        "lca_kernel.runtime.observability",
    }
)
_ASSEMBLY_OBSERVABILITY_NAMES = frozenset(
    {
        "canonical_digest",
        "RunJournalFactory",
        "CursorRecord",
        "NullPersistenceCoordinator",
        "LineCoalescer",
        "NdjsonSerializer",
        "NullStorage",
        "SpineEmitter",
        "StandardDriver",
        "WritableFaceRegistry",
        "ObservabilityRuntime",
        "_StepTreeBundle",
    }
)


def test_session_builder_does_not_publish_or_emit_diagnostics() -> None:
    """The builder owns assembly only, not publication or observability writes."""
    # 自 291a55c0d 起 flat builder.py 已合并为 builder/builder.py 子包。
    builder = _TRANSPORT_SESSION / "builder" / "builder.py"
    source = builder.read_text(encoding="utf-8")

    assert "registry.put" not in source
    assert "record_runtime" not in source
    observability_imports = _observability_from_imports(builder)
    assert set(observability_imports) <= _ASSEMBLY_OBSERVABILITY_MODULES, (
        "builder gained non-assembly observability imports: "
        f"{sorted(set(observability_imports) - _ASSEMBLY_OBSERVABILITY_MODULES)}"
    )
    for module, imported_names in observability_imports.items():
        unexpected = [n for n in imported_names if n not in _ASSEMBLY_OBSERVABILITY_NAMES]
        assert not unexpected, f"{module} imported non-assembly names: {unexpected}"
