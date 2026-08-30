"""Tests for lca.layer0_infra.tools.contract."""

from __future__ import annotations

import unittest

from lca.layer0_infra.tools.contract import (
    COMMON,
    REGISTRY,
    FieldSpec,
    RenderContract,
    contract,
    get_contract,
    render_registry_to_ts,
    sandbox_state,
    skill_args,
    skill_state,
)


def _save_registry() -> dict:
    """Snapshot REGISTRY so tests can restore it."""
    return dict(REGISTRY)


def _restore_registry(snapshot: dict) -> None:
    """Restore REGISTRY from a snapshot."""
    REGISTRY.clear()
    REGISTRY.update(snapshot)


_SAMPLE_C = RenderContract(
    tool_name="test_tool",
    identifier="test-id",
    api_name="testTool",
    args=(FieldSpec("name", "name", "string", "argument"),),
    state=(),
    streaming=(),
    content_field=None,
    wait_for=(),
)


class TestRegisterAndLookup(unittest.TestCase):
    def setUp(self) -> None:
        self._snap = _save_registry()

    def tearDown(self) -> None:
        _restore_registry(self._snap)

    def test_register_and_lookup(self) -> None:
        c = RenderContract(
            tool_name="lookup_test",
            identifier="id",
            api_name="lookupTest",
        )

        @contract(c)
        class Dummy: ...

        self.assertIs(get_contract("lookup_test"), c)

    def test_duplicate_registration_raises(self) -> None:
        c1 = RenderContract(tool_name="dup", identifier="a", api_name="a")
        c2 = RenderContract(tool_name="dup", identifier="b", api_name="b")

        @contract(c1)
        class D1: ...

        with self.assertRaises(KeyError):

            @contract(c2)
            class D2: ...


class TestFieldSpec(unittest.TestCase):
    def test_field_rename_preserves_other_fields(self) -> None:
        f = FieldSpec("x", "X", "string", "argument", True, "desc")
        g = f.rename("Y")
        self.assertEqual(g.wire_key, "Y")
        self.assertEqual(g.python_key, f.python_key)
        self.assertEqual(g.kind, f.kind)
        self.assertEqual(g.source, f.source)
        self.assertEqual(g.required, f.required)
        self.assertEqual(g.description, f.description)

    def test_field_optional_marks_not_required(self) -> None:
        f = FieldSpec("x", "X", "int", "observation", True)
        g = f.optional()
        self.assertFalse(g.required)
        self.assertEqual(g.python_key, f.python_key)
        self.assertEqual(g.wire_key, f.wire_key)


class TestCommonSchema(unittest.TestCase):
    def test_common_schema_has_minimum_fields(self) -> None:
        self.assertGreaterEqual(len(COMMON), 35)
        for key in (
            "command",
            "language",
            "code",
            "skill_id",
            "path",
            "query",
            "timeout",
            "name",
            "identifier",
            "stdout",
            "stderr",
            "files",
            "exit_code",
            "mounted_files",
        ):
            self.assertIn(key, COMMON)
        self.assertEqual(COMMON["skill_id"].wire_key, "id")


class TestCodegen(unittest.TestCase):
    def setUp(self) -> None:
        self._snap = _save_registry()

    def tearDown(self) -> None:
        _restore_registry(self._snap)

    def test_codegen_is_deterministic(self) -> None:
        REGISTRY.clear()
        REGISTRY["t"] = _SAMPLE_C
        a = render_registry_to_ts()
        b = render_registry_to_ts()
        self.assertEqual(a, b)

    def test_codegen_sorts_by_tool_name(self) -> None:
        REGISTRY.clear()
        for name in ("zebra", "alpha", "mango"):
            REGISTRY[name] = RenderContract(tool_name=name, identifier="x", api_name=name)
        out = render_registry_to_ts()
        pos_a = out.index('"alpha"')
        pos_m = out.index('"mango"')
        pos_z = out.index('"zebra"')
        self.assertLess(pos_a, pos_m)
        self.assertLess(pos_m, pos_z)

    def test_codegen_handles_empty_registry(self) -> None:
        out = render_registry_to_ts({})
        self.assertIn("export const CONTRACTS", out)
        self.assertIn("ToolRenderContract", out)

    def test_codegen_empty_registry_is_valid_ts(self) -> None:
        out = render_registry_to_ts({})
        # Must have `{}` as the body, followed by `as const;`
        self.assertIn("= {", out)
        self.assertIn("} as const;", out)
        # Must NOT have the commented-out `as const` bug
        self.assertNotIn("= \n  // ", out)


class TestBuiltinHelpers(unittest.TestCase):
    def test_builtin_helpers_return_tuples(self) -> None:
        for fn in (sandbox_state, skill_args, skill_state):
            result = fn()
            self.assertIsInstance(result, tuple)
            self.assertGreater(len(result), 0)
            for field in result:
                self.assertIsInstance(field, FieldSpec)


class TestContractDecorator(unittest.TestCase):
    def setUp(self) -> None:
        self._snap = _save_registry()

    def tearDown(self) -> None:
        _restore_registry(self._snap)

    def test_contract_decorator_returns_class(self) -> None:
        c = RenderContract(tool_name="cls_test", identifier="id", api_name="cls")

        @contract(c)
        class MyTool:
            pass

        self.assertIs(get_contract("cls_test"), c)
        self.assertEqual(MyTool.__name__, "MyTool")


if __name__ == "__main__":
    unittest.main()
