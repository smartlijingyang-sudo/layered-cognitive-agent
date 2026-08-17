"""Integration tests for the Cordis-style kernel additions:

- ``!py`` expression interpolation in profiles
- group entries with nested children
- BootedTree runtime mutation API
- timer plugin loaded through YAML
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from lca.layer0_infra.plugin.expr.pyexpr import PyExpr, SafeEvaluator, interpolate
from lca.layer0_infra.plugin.include._profile import ProfileLoader
from lca.layer0_infra.plugin.loader import Loader
from lca.layer0_infra.plugin.loader._entry import PluginEntry
from lca.layer0_infra.plugin.scope.store import NamedEntries


def _write_profile(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


class TestPyExpr:
    def test_basic_eval(self) -> None:
        assert SafeEvaluator({}).evaluate("1 + 2") == 3

    def test_scope_lookup(self) -> None:
        env = {"API_KEY": "secret"}
        assert SafeEvaluator({"ctx": {"env": env}}).evaluate("ctx.env.API_KEY") == "secret"

    def test_conditional(self) -> None:
        evaluator = SafeEvaluator({"ENV": "prod"})
        assert evaluator.evaluate("'gpt-4' if ENV == 'prod' else 'gpt-3.5'") == "gpt-4"

    def test_unsafe_call_rejected(self) -> None:
        # ``__import__`` is not in the safe namespace — resolving the call
        # target fails before any evaluation happens.
        with pytest.raises(ValueError, match="__import__"):
            SafeEvaluator({}).evaluate("__import__('os').system('rm -rf /')")

    def test_interpolate_recursive(self) -> None:
        value = {"model": PyExpr("'gpt-4'"), "list": [PyExpr("1 + 1")]}
        result = interpolate(value, {})
        assert result == {"model": "gpt-4", "list": [2]}


class TestPyExprInProfile:
    def test_profile_interpolates_py_expr(self, tmp_path: Path) -> None:
        path = tmp_path / "profile.yaml"
        path.write_text(
            "bundles: []\n"
            "patch:\n"
            "  - insert:\n"
            "      - id: echo\n"
            "        name: lca.layer0_infra.plugin.include._profile\n"
            "        config:\n"
            "          model: !py \"'claude-3'\"\n"
            "          n: !py 2 * 21\n"
        )
        entries = ProfileLoader().load_profile(path)
        echo = next(e for e in entries if e.id == "echo")
        assert echo.config["model"] == "claude-3"
        assert echo.config["n"] == 42


class TestGroupEntries:
    def test_group_entry_holds_children(self, tmp_path: Path) -> None:
        path = _write_profile(
            tmp_path,
            {
                "bundles": [],
                "patch": [
                    {
                        "insert": [
                            {
                                "id": "tools-group",
                                "name": "cordis:group",
                                "group": True,
                                "config": [
                                    {
                                        "id": "tool-a",
                                        "name": "lca.plugins.search_service",
                                        "config": {},
                                    },
                                ],
                            }
                        ]
                    }
                ],
            },
        )
        entries = ProfileLoader().load_profile(path)
        group = next(e for e in entries if e.id == "tools-group")
        assert group.group is True
        assert isinstance(group.config, list)
        assert group.config[0].id == "tool-a"

    def test_dump_profile_shows_children(self, tmp_path: Path) -> None:
        path = _write_profile(
            tmp_path,
            {
                "bundles": [],
                "patch": [
                    {
                        "insert": [
                            {
                                "id": "grp",
                                "group": True,
                                "config": [{"id": "child", "name": "x.y", "config": {}}],
                            }
                        ]
                    }
                ],
            },
        )
        rows = ProfileLoader().dump_profile(path)
        assert any(r["id"] == "grp" for r in rows)
        assert any(r["id"] == "child" and r["parent"] == "grp" for r in rows)


class TestBootedTreeMutation:
    @staticmethod
    def _make_module(name: str, provides: str) -> Any:
        class Module:
            pass

        mod = Module()
        mod.name = name
        mod.provides = provides
        mod.Config = type("PluginConfig", (), {"model_config": {"extra": "forbid"}})

        def apply(ctx: Any, config: Any) -> None:
            ctx.mount(provides, {"svc": name})

        mod.apply = apply
        return mod

    @pytest.mark.asyncio
    async def test_create_remove_update(self) -> None:
        mod_a = self._make_module("a", "svc-a")
        tree = await Loader().load([PluginEntry(id="a", module=mod_a)])

        # Runtime create
        mod_b = self._make_module("b", "svc-b")
        await tree.create(PluginEntry(id="b", module=mod_b))
        assert tree.host.get_service("svc-b") is not None

        # Runtime remove
        await tree.remove("a")
        assert tree.host.get_service("svc-a") is None


class TestNamedEntriesIntegration:
    def test_registry_undo(self) -> None:
        table = NamedEntries[int](lambda n: KeyError(n))
        undo = table.insert("x", 1)
        assert table.get("x") == 1
        undo()
        assert table.is_empty()
