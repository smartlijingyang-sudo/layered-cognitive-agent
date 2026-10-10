"""JournalSchema registry —— 读侧 (ADR-0096 MVA-1)。

写侧：``lca.plugins.observability.journal.schema_seam`` 在 boot 时注册
各版本 schema 并把 registry 经 :func:`install_journal_schema_registry`
装进这里；读侧：``journal_io`` 等 infrastructure 代码经
:func:`resolve_journal_schema` 取 schema，不再直引 ``lca.plugins``
（包契约 pin）。

未装配时回退内置默认 registry（含 ``v2.0.0``）—— 与 seam 引入前
``EnvelopeV2Schema()`` 直构行为一致，零行为变更。
"""

from __future__ import annotations

from lca.contracts.observability.schemas.envelope_v2_schema import EnvelopeV2Schema
from lca.contracts.observability.schemas.v2 import SCHEMA_VERSION, JournalSchema


class JournalSchemaRegistry:
    """Named registry of JournalSchema implementations."""

    def __init__(self) -> None:
        self._schemas: dict[str, JournalSchema] = {}

    def name(self) -> str:
        return "JournalSchemaRegistry"

    def register(self, version: str, schema: JournalSchema) -> None:
        self._schemas[version] = schema

    def get(self, version: str) -> JournalSchema | None:
        return self._schemas.get(version)

    def all(self) -> dict[str, JournalSchema]:
        return dict(self._schemas)


def _default_registry() -> JournalSchemaRegistry:
    registry = JournalSchemaRegistry()
    registry.register(SCHEMA_VERSION, EnvelopeV2Schema())
    return registry


_DEFAULT_REGISTRY = _default_registry()

_active_registry: JournalSchemaRegistry | None = None


def install_journal_schema_registry(
    registry: JournalSchemaRegistry | None,
) -> JournalSchemaRegistry | None:
    """安装进程级 schema registry；返回旧值以便调用方恢复（测试常用）。"""
    global _active_registry
    previous = _active_registry
    _active_registry = registry
    return previous


def resolve_journal_schema(version: str = SCHEMA_VERSION) -> JournalSchema:
    """按版本取 schema；未装配时用内置默认 registry。

    已装配但 registry 缺该版本 → LookupError（接线 bug，fail-fast）。
    """
    registry = _active_registry if _active_registry is not None else _DEFAULT_REGISTRY
    schema = registry.get(version)
    if schema is None:
        raise LookupError(
            f"journal schema {version!r} not registered; available: {sorted(registry.all())}"
        )
    return schema


__all__ = [
    "JournalSchemaRegistry",
    "install_journal_schema_registry",
    "resolve_journal_schema",
]
