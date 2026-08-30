"""Tests that all tool contracts are properly registered in REGISTRY."""

from __future__ import annotations

import unittest

# Import sandbox_contracts to populate dynamic-tool contracts.
import lca.infrastructure.tools.contract.sandbox_contracts

# Import skill tool modules — their @contract decorators populate REGISTRY.
import lca.infrastructure.tools.skills.activate_tool
import lca.infrastructure.tools.skills.exec_tool
import lca.infrastructure.tools.skills.import_tool
import lca.infrastructure.tools.skills.read_reference_tool
import lca.infrastructure.tools.skills.search_tool  # noqa: F401
from lca.infrastructure.tools.contract.codegen_ts import render_registry_to_ts
from lca.infrastructure.tools.contract.render import REGISTRY, get_contract


class TestSkillToolContracts(unittest.TestCase):
    """All five skill tools must have contracts in REGISTRY."""

    SKILL_TOOL_NAMES = (
        "activate_skill",
        "run_skill_script",
        "read_skill_reference",
        "import_skill",
        "search_skill",
    )

    def test_all_skill_tools_have_contracts(self) -> None:
        for name in self.SKILL_TOOL_NAMES:
            with self.subTest(tool=name):
                c = get_contract(name)
                self.assertIsNotNone(c, f"Missing contract for {name}")

    def test_skill_id_renames_correctly_for_activate(self) -> None:
        c = get_contract("activate_skill")
        assert c is not None
        self.assertGreaterEqual(len(c.args), 1)
        self.assertEqual(c.args[0].wire_key, "name")

    def test_skill_id_renames_correctly_for_read_reference(self) -> None:
        c = get_contract("read_skill_reference")
        assert c is not None
        self.assertGreaterEqual(len(c.args), 1)
        self.assertEqual(c.args[0].wire_key, "id")

    def test_skill_identifiers_correct(self) -> None:
        for name in ("activate_skill", "run_skill_script", "read_skill_reference"):
            c = get_contract(name)
            assert c is not None
            self.assertEqual(c.identifier, "lobe-skills")
        for name in ("import_skill", "search_skill"):
            c = get_contract(name)
            assert c is not None
            self.assertEqual(c.identifier, "lobe-skill-store")


class TestSandboxToolContracts(unittest.TestCase):
    """Cloud sandbox tools must have contracts with identifier='lobe-cloud-sandbox'."""

    CLOUD_TOOLS = (
        "executeCode",
        "runCommand",
        "listFiles",
        "readFile",
        "writeFile",
        "editFile",
        "searchFiles",
        "moveFiles",
        "grepContent",
        "globFiles",
        "getCommandOutput",
        "killCommand",
        "exportFile",
    )

    def test_sandbox_tools_have_contracts(self) -> None:
        for name in self.CLOUD_TOOLS:
            with self.subTest(tool=name):
                c = get_contract(name)
                self.assertIsNotNone(c, f"Missing contract for {name}")
                self.assertEqual(c.identifier, "lobe-cloud-sandbox")

    def test_sandbox_api_names_match_tool_names(self) -> None:
        for name in self.CLOUD_TOOLS:
            with self.subTest(tool=name):
                c = get_contract(name)
                assert c is not None
                self.assertEqual(c.api_name, name)


class TestLocalSystemToolContracts(unittest.TestCase):
    """Local system tools must have contracts with identifier='lobe-local-system'."""

    LOCAL_TOOLS = (
        "local_executeCode",
        "local_runCommand",
        "local_listFiles",
        "local_readFile",
        "local_writeFile",
        "local_editFile",
        "local_searchFiles",
        "local_moveFiles",
        "local_grepContent",
        "local_globFiles",
        "local_getCommandOutput",
        "local_killCommand",
    )

    def test_local_system_tools_have_contracts(self) -> None:
        for name in self.LOCAL_TOOLS:
            with self.subTest(tool=name):
                c = get_contract(name)
                self.assertIsNotNone(c, f"Missing contract for {name}")
                self.assertEqual(c.identifier, "lobe-local-system")

    def test_local_tools_have_no_export(self) -> None:
        self.assertIsNone(get_contract("local_exportFile"))


class TestWebSearchContract(unittest.TestCase):
    def test_web_search_has_contract(self) -> None:
        c = get_contract("search")
        self.assertIsNotNone(c)
        assert c is not None
        self.assertEqual(c.identifier, "lobe-web-browsing")
        self.assertEqual(c.api_name, "search")


class TestAskUserContract(unittest.TestCase):
    def test_ask_user_question_has_contract(self) -> None:
        c = get_contract("askUserQuestion")
        self.assertIsNotNone(c)
        assert c is not None
        self.assertEqual(c.identifier, "lobe-user-interaction")
        self.assertEqual(c.api_name, "askUserQuestion")

    def test_import_skill_content_field_matches_state(self) -> None:
        c = get_contract("import_skill")
        assert c is not None
        self.assertEqual(c.content_field, "content")
        state_keys = [f.python_key for f in c.state]
        self.assertIn("content", state_keys)


class TestRegistryIntegrity(unittest.TestCase):
    def test_no_duplicate_tool_names_in_registry(self) -> None:
        # REGISTRY is a dict, so keys are already unique; verify it's not empty.
        self.assertGreater(len(REGISTRY), 0)

    def test_codegen_with_full_registry_contains_all_tools(self) -> None:
        ts = render_registry_to_ts()
        for name in REGISTRY:
            with self.subTest(tool=name):
                self.assertIn(f'"{name}"', ts)


if __name__ == "__main__":
    unittest.main()
