"""lca-run-locator-seam 装配测试(ADR-0065 PR-5)。"""

from __future__ import annotations

import asyncio

from lca.contracts.observability.run_locator import RunLocator
from lca.infrastructure.observability.backends.run_locator_fs import FilesystemRunLocator


def _invoke_seam_setup() -> dict[str, object]:
    from lca.plugins.observability.run_locator_seam import Config
    from lca.plugins.observability.run_locator_seam import setup as seam_setup

    provided: dict[str, object] = {}

    class FakeCtx:
        def provide(self, key: str, value: object) -> None:
            provided[key] = value

    setup_fn = getattr(seam_setup, "setup", seam_setup)
    asyncio.run(setup_fn(FakeCtx(), Config()))
    return provided


def test_seam_provides_filesystem_locator() -> None:
    provided = _invoke_seam_setup()
    assert "run_locator" in provided
    assert isinstance(provided["run_locator"], FilesystemRunLocator)


def test_seam_locator_satisfies_protocol() -> None:
    provided = _invoke_seam_setup()
    locator = provided["run_locator"]
    assert isinstance(locator, RunLocator)


def test_seam_meta_manifest_is_correct() -> None:
    from lca.plugins.observability.run_locator_seam import setup as seam_setup

    meta = getattr(seam_setup, "meta", {})
    assert meta.get("id") == "lca-run-locator-seam"
    assert "run_locator" in meta.get("provides", [])
    assert meta.get("layer") == "L0"
