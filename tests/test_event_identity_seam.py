"""lca-event-identity-seam 装配测试 (ADR-0096 MVA-2 + ADR-0097).

验证 seam 在 boot 时把 ``event_identities`` capability 注册到 Context，并暴露
空 ``NamedRegistry``。后续 MVA-2 Task 3 会注入
``providers/event_identity/stable_ulid`` 的 ``StableUlidIdentity`` 实现，
本测试只验证 seam 骨架。
"""

from __future__ import annotations

import asyncio


def _invoke_seam_setup() -> dict[str, object]:
    """``@plugin`` 装饰后 ``setup`` 是 Plugin 对象；真实函数挂在 ``.setup`` 上。"""
    from lca.plugins.seam_definitions.observability.event_identity import Config
    from lca.plugins.seam_definitions.observability.event_identity import (
        setup as seam_setup,
    )

    provided: dict[str, object] = {}

    class FakeCtx:
        def provide(self, key: str, value: object) -> None:
            provided[key] = value

    setup_fn = getattr(seam_setup, "setup", seam_setup)
    asyncio.run(setup_fn(FakeCtx(), Config()))
    return provided


def test_event_identity_seam_provides_registry() -> None:
    provided = _invoke_seam_setup()
    assert "event_identities" in provided
    registry = provided["event_identities"]
    assert registry is not None


def test_event_identity_registry_is_named_registry() -> None:
    from lca.infrastructure.observability import NamedRegistry

    provided = _invoke_seam_setup()
    registry = provided["event_identities"]
    assert isinstance(registry, NamedRegistry)


def test_event_identity_seam_meta_manifest_is_correct() -> None:
    """Seam 的 cordis Plugin 元数据必须与 @plugin 装饰器一致 (ADR-0061 / 0062)。"""
    from lca.plugins.seam_definitions.observability.event_identity import (
        setup as seam_setup,
    )

    meta = getattr(seam_setup, "meta", {})
    assert meta.get("id") == "lca-event-identity-seam"
    assert "event_identities" in meta.get("provides", [])
    assert meta.get("layer") == "L0"
    assert meta.get("kind") == "seam"
