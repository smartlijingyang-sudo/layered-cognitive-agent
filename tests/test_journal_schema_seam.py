"""lca-journal-schema-seam 装配测试 (ADR-0096 MVA-1).

验证 seam 在 boot 时把 ``journal_schemas`` capability 注册到 Context，并暴露
``JournalSchemaRegistry`` placeholder。后续 MVA-1 Task 2 / Task 3 会在
``lca/contracts/observability/schemas`` 引入正式 Pydantic v2 model 和
``providers/journal_schema/v2`` provider，本测试只验证 seam 骨架。
"""

from __future__ import annotations

import asyncio


def _invoke_seam_setup() -> dict[str, object]:
    """``@plugin`` 装饰后 ``setup`` 是 Plugin 对象；真实函数挂在 ``.setup`` 上。"""
    from lca.plugins.observability.journal_schema_seam import Config
    from lca.plugins.observability.journal_schema_seam import (
        setup as seam_setup,
    )

    provided: dict[str, object] = {}

    class FakeCtx:
        def provide(self, key: str, value: object) -> None:
            provided[key] = value

    setup_fn = getattr(seam_setup, "setup", seam_setup)
    asyncio.run(setup_fn(FakeCtx(), Config()))
    return provided


def test_journal_schema_seam_provides_registry() -> None:
    provided = _invoke_seam_setup()
    assert "journal_schemas" in provided
    registry = provided["journal_schemas"]
    assert registry is not None


def test_journal_schema_registry_name() -> None:
    provided = _invoke_seam_setup()
    registry = provided["journal_schemas"]
    assert registry.name() == "JournalSchemaRegistry"


def test_journal_schema_seam_meta_manifest_is_correct() -> None:
    """Seam 的 cordis Plugin 元数据必须与 @plugin 装饰器一致 (ADR-0061 / 0062)。"""
    from lca.plugins.observability.journal_schema_seam import (
        setup as seam_setup,
    )

    meta = getattr(seam_setup, "meta", {})
    assert meta.get("id") == "lca-journal-schema-seam"
    assert "journal_schemas" in meta.get("provides", [])
    assert meta.get("layer") == "L0"
    assert meta.get("kind") == "seam"
