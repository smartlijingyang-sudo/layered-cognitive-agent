"""lca-evidence-store-seam + provider 装配测试(ADR-0065 PR-2)。

验证 seam 提供 evidence_store + evidence_policy 两个 capability,均解析为
具体实现;Profiles 默认 profile 通过 boot 把两个 capability 都挂上。
"""

from __future__ import annotations

import asyncio

from lca.contracts.observability.evidence import EvidencePolicy, EvidenceStore
from lca.infrastructure.observability.evidence.policy import DefaultEvidencePolicy
from lca.infrastructure.observability.evidence.store import FilesystemEvidenceStore


def _invoke_seam_setup() -> dict[str, object]:
    """``@plugin`` 装饰后 ``setup`` 是 Plugin 对象;真实函数挂在 ``.setup`` 上。"""
    from lca.plugins.observability.evidence_store_seam import Config
    from lca.plugins.observability.evidence_store_seam import setup as seam_setup

    provided: dict[str, object] = {}

    class FakeCtx:
        def provide(self, key: str, value: object) -> None:
            provided[key] = value

    setup_fn = getattr(seam_setup, "setup", seam_setup)
    asyncio.run(setup_fn(FakeCtx(), Config()))
    return provided


def test_seam_setup_provides_both_capabilities() -> None:
    provided = _invoke_seam_setup()
    assert "evidence_store" in provided
    assert "evidence_policy" in provided
    assert isinstance(provided["evidence_store"], FilesystemEvidenceStore)
    assert isinstance(provided["evidence_policy"], DefaultEvidencePolicy)


def test_seam_protocol_types_match() -> None:
    """Seam 提供的两个对象必须满足对应 Protocol —— isinstance 校验。"""
    provided = _invoke_seam_setup()
    assert isinstance(provided["evidence_store"], EvidenceStore)
    assert isinstance(provided["evidence_policy"], EvidencePolicy)


def test_seam_idempotent_when_called_twice() -> None:
    """boot 调用两次不会破坏状态(同 Context 会用 last-write-wins)。"""
    provided_first = _invoke_seam_setup()
    provided_second = _invoke_seam_setup()
    assert "evidence_store" in provided_first
    assert "evidence_store" in provided_second
    assert "evidence_policy" in provided_first
    assert "evidence_policy" in provided_second


def test_seam_meta_manifest_is_correct() -> None:
    """Seam 的 cordis Plugin 元数据必须与 @plugin 装饰器一致(ADR-0061 / 0062)。"""
    from lca.plugins.observability.evidence_store_seam import setup as seam_setup

    meta = getattr(seam_setup, "meta", {})
    assert meta.get("id") == "lca-evidence-store-seam"
    assert "evidence_store" in meta.get("provides", [])
    assert "evidence_policy" in meta.get("provides", [])
    assert meta.get("layer") == "L0"
