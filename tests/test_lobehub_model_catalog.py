"""Contract: LobeHub chat picker only exposes solo / team / auto."""

from __future__ import annotations

from pathlib import Path

from gateway.modes import LCA_UI_MODELS

_CATALOG = Path("deploy/lobehub/patches/provider/lca_model_catalog.py").read_text(encoding="utf-8")
_DRIVER = Path("deploy/lobehub/patches/runtime/lca_run_driver.py").read_text(encoding="utf-8")
_CUSTOMIZATIONS = Path("deploy/lobehub/CUSTOMIZATIONS.md").read_text(encoding="utf-8")
_ENV = Path("deploy/lobehub/.env.lca").read_text(encoding="utf-8")


def test_ui_catalog_is_solo_team_auto() -> None:
    assert LCA_UI_MODELS == ("solo", "team", "auto")
    for model in LCA_UI_MODELS:
        assert f"id: '{model}'" in _CATALOG
    assert "resolveLcaChatModel" in _CATALOG
    assert "qwen" not in _CATALOG.lower()
    assert "gpt-" not in _CATALOG


def test_unknown_model_remaps_to_solo() -> None:
    assert "every chat is a Run" in _DRIVER
    assert "model === 'team' || model === 'auto' ? model : 'solo'" in _DRIVER
    assert "model: lcaModel" in _DRIVER


def test_env_defaults_to_solo_not_qwen() -> None:
    assert "DEFAULT_AGENT_CONFIG=model=solo;provider=openai" in _ENV
    assert "ENABLED_QWEN=0" in _ENV
    assert "qwen3.7-plus" not in _ENV


def test_catalog_is_registered() -> None:
    assert "| `lca_model_catalog`" in _CUSTOMIZATIONS
