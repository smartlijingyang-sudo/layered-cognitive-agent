"""Unit tests for ``coerce_mode`` — the L0 mode-narrowing helper.

The helper lives under ``lca.application.runtime.adapters`` whose
package ``__init__`` eagerly imports the full application API and
therefore ``cordis``. Loading ``lca.application.runtime.adapters._mode``
through the package import chain fails in CI environments without
``cordis`` installed. To stay runnable under such environments we load
the module file directly with ``importlib``.

These are pure-function tests; they never touch the adapters' sibling
modules that depend on the application runtime.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[4]
_MODE_PATH = _REPO / "lca" / "application" / "runtime" / "adapters" / "_mode.py"


@pytest.fixture
def coerce_mode() -> Iterator[object]:
    """Yield the ``coerce_mode`` function without importing ``lca.application``.

    Bypasses ``lca/application/__init__.py`` (which transitively imports
    ``cordis``) so the test runs in any environment.
    """
    spec = importlib.util.spec_from_file_location("_lca_adapters_mode", _MODE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module.coerce_mode
    finally:
        sys.modules.pop(spec.name, None)


class TestCoerceModeHappyPath:
    def test_solo_passes_through(self, coerce_mode: object) -> None:
        """``"solo"`` returns ``"solo"`` unchanged."""
        assert coerce_mode("solo") == "solo"  # type: ignore[operator]

    def test_team_passes_through(self, coerce_mode: object) -> None:
        """``"team"`` returns ``"team"`` unchanged."""
        assert coerce_mode("team") == "team"  # type: ignore[operator]


class TestCoerceModeRejection:
    @pytest.mark.parametrize(
        "value",
        [
            "solo-team",
            "SOLO",
            "Solo",
            "  solo  ",
            "",
        ],
    )
    def test_rejects_non_literal_strings(self, coerce_mode: object, value: str) -> None:
        """Strings outside the literal set raise ``ValueError``."""
        with pytest.raises(ValueError, match="mode"):
            coerce_mode(value)  # type: ignore[operator]

    @pytest.mark.parametrize("value", [None, 0, 1, True, False, ("solo",), {"solo"}])
    def test_rejects_non_strings(self, coerce_mode: object, value: object) -> None:
        """Non-string values raise ``ValueError`` (the contract is literal)."""
        with pytest.raises(ValueError, match="mode"):
            coerce_mode(value)  # type: ignore[operator]


class TestCoerceModeFieldName:
    def test_custom_field_name_appears_in_message(self, coerce_mode: object) -> None:
        """The ``field`` keyword is included in the rejection message."""
        with pytest.raises(ValueError, match="my_field"):
            coerce_mode("nope", field="my_field")  # type: ignore[operator]
