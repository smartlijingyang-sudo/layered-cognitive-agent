"""Unit tests for ``coerce_mode`` — the L0 mode-narrowing helper."""

from __future__ import annotations

import pytest

from lca.application.runtime.adapters import coerce_mode


class TestCoerceModeHappyPath:
    def test_solo_passes_through(self) -> None:
        """``"solo"`` returns ``"solo"`` unchanged."""
        assert coerce_mode("solo") == "solo"

    def test_team_passes_through(self) -> None:
        """``"team"`` returns ``"team"`` unchanged."""
        assert coerce_mode("team") == "team"


class TestCoerceModeRejection:
    def test_none_rejected(self) -> None:
        """``None`` is not a string."""
        with pytest.raises(ValueError, match=r"RunIntent\.mode must be one of"):
            coerce_mode(None)

    def test_bool_rejected(self) -> None:
        """``True``/``False`` rejected even though ``bool`` is a subclass of ``int``."""
        with pytest.raises(ValueError, match=r"RunIntent\.mode must be one of"):
            coerce_mode(True)
        with pytest.raises(ValueError, match=r"RunIntent\.mode must be one of"):
            coerce_mode(False)

    def test_int_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"RunIntent\.mode must be one of"):
            coerce_mode(1)

    def test_arbitrary_string_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"RunIntent\.mode must be one of"):
            coerce_mode("parallel")
        with pytest.raises(ValueError, match=r"RunIntent\.mode must be one of"):
            coerce_mode("swarm")
        with pytest.raises(ValueError, match=r"RunIntent\.mode must be one of"):
            coerce_mode("")

    def test_field_name_appears_in_error_message(self) -> None:
        """Custom ``field=`` name surfaces in the :class:`ValueError`."""
        with pytest.raises(ValueError) as excinfo:
            coerce_mode("invalid", field="custom_field")
        assert "RunIntent.custom_field must be one of" in str(excinfo.value)
