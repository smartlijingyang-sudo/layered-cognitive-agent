"""OfficeCLI Office plane — bundled skill seed + routing (ADR-0054)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lca.contracts.models.core.sandbox import SANDBOX_PREINSTALLED_CLI_TOOLS
from lca.layer0_infra.skills.bundled import (
    OFFICECLI_SKILL_ID,
    default_bundled_skills_root,
    ensure_bundled_skills,
)
from lca.layer0_infra.skills.disk_store import DiskSkillPackageStore, content_hash
from lca.layer0_infra.skills.settings import SkillSettings


class TestOfficecliContracts(unittest.TestCase):
    def test_officecli_listed_as_preinstalled_cli(self) -> None:
        self.assertIn("officecli", SANDBOX_PREINSTALLED_CLI_TOOLS)


class TestBundledOfficecliSkill(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = DiskSkillPackageStore(SkillSettings(cache_dir=Path(self._tmp.name)))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_repo_ships_officecli_skill_pack(self) -> None:
        root = default_bundled_skills_root()
        skill_md = root / OFFICECLI_SKILL_ID / "SKILL.md"
        self.assertTrue(skill_md.is_file(), f"missing {skill_md}")
        text = skill_md.read_text(encoding="utf-8")
        self.assertIn("officecli", text.lower())
        self.assertIn("outputs/", text)
        self.assertNotIn("/mnt/data", text)
        self.assertIn("--json", text)
        self.assertNotIn("curl -fsSL", text)

    def test_ensure_installs_officecli(self) -> None:
        written = ensure_bundled_skills(self.store, root=default_bundled_skills_root())
        self.assertIn(OFFICECLI_SKILL_ID, written)
        package = self.store.get(OFFICECLI_SKILL_ID)
        self.assertEqual(package.skill_id, OFFICECLI_SKILL_ID)
        self.assertIn("run_command", package.content)
        self.assertTrue(package.source_url.startswith("bundled:"))

    def test_ensure_is_idempotent_when_hash_matches(self) -> None:
        ensure_bundled_skills(self.store, root=default_bundled_skills_root())
        second = ensure_bundled_skills(self.store, root=default_bundled_skills_root())
        self.assertEqual(second, ())

    def test_ensure_refreshes_on_content_change(self) -> None:
        bundle = Path(self._tmp.name) / "bundle" / "demo-skill"
        bundle.mkdir(parents=True)
        skill_md = bundle / "SKILL.md"
        skill_md.write_text(
            "---\nname: demo\ndescription: v1\nversion: 1\n---\n# body1\n",
            encoding="utf-8",
        )
        root = bundle.parent
        self.assertEqual(ensure_bundled_skills(self.store, root=root), ("demo-skill",))
        skill_md.write_text(
            "---\nname: demo\ndescription: v2\nversion: 2\n---\n# body2\n",
            encoding="utf-8",
        )
        refreshed = ensure_bundled_skills(self.store, root=root)
        self.assertEqual(refreshed, ("demo-skill",))
        package = self.store.get("demo-skill")
        self.assertIn("body2", package.content)
        self.assertEqual(
            package.content_hash,
            content_hash(skill_md.read_text(encoding="utf-8").encode("utf-8")),
        )


if __name__ == "__main__":
    unittest.main()
