"""lca-w3c-validator-seam 装配测试(ADR-0065 PR-7)。"""

from __future__ import annotations

import asyncio

from lca.contracts.observability.w3c_trace_context import W3CTraceContextValidator
from lca.infrastructure.observability.w3c_validator import DefaultW3CValidator


def _invoke_seam_setup() -> dict[str, object]:
    from lca.plugins.seam_definitions.observability.w3c_validator import Config
    from lca.plugins.seam_definitions.observability.w3c_validator import setup as seam_setup

    provided: dict[str, object] = {}

    class FakeCtx:
        def provide(self, key: str, value: object) -> None:
            provided[key] = value

    setup_fn = getattr(seam_setup, "setup", seam_setup)
    asyncio.run(setup_fn(FakeCtx(), Config()))
    return provided


def test_seam_provides_default_validator() -> None:
    provided = _invoke_seam_setup()
    assert "w3c_trace_context_validator" in provided
    assert isinstance(provided["w3c_trace_context_validator"], DefaultW3CValidator)


def test_seam_validator_satisfies_protocol() -> None:
    provided = _invoke_seam_setup()
    assert isinstance(provided["w3c_trace_context_validator"], W3CTraceContextValidator)


def test_seam_meta_manifest_is_correct() -> None:
    from lca.plugins.seam_definitions.observability.w3c_validator import setup as seam_setup

    meta = getattr(seam_setup, "meta", {})
    assert meta.get("id") == "lca-w3c-validator-seam"
    assert "w3c_trace_context_validator" in meta.get("provides", [])
    assert meta.get("layer") == "L0"
