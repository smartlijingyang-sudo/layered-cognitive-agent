"""Operational skill library — store, importer, tools (ADR-0048)."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from lca.contracts.protocols.operational_skills import SkillImportError, SkillNotFoundError
from lca.layer0_infra.skills.activation_scope import (
    activated_skills_scope,
    register_activated,
    resolve_skill_for_exec,
)
from lca.layer0_infra.skills.disk_store import DiskSkillPackageStore, sanitize_skill_id
from lca.layer0_infra.skills.http_importer import HttpSkillImporter
from lca.layer0_infra.skills.market_auth import (
    clear_market_token_cache,
    create_client_assertion,
    resolve_m2m_credentials,
    resolve_market_access_token,
    token_endpoint_for,
)
from lca.layer0_infra.skills.settings import SkillSettings
from lca.layer0_infra.skills.zip_security import extract_zip_bytes, find_skill_markdown
from lca.layer0_infra.tools.default_set import build_default_tools
from lca.layer0_infra.tools.skills.activate_tool import SkillActivateTool
from lca.layer0_infra.tools.skills.import_tool import SkillImportTool
from lca.layer0_infra.tools.skills.read_reference_tool import SkillReadReferenceTool
from lca.layer0_infra.tools.skills.search_tool import SkillSearchTool


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    return buf.getvalue()


class TestZipSecurity(unittest.TestCase):
    def test_extract_rejects_traversal(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../evil.txt", "x")
            zf.writestr("SKILL.md", "---\nname: t\ndescription: d\n---\nbody")
        with self.assertRaises(SkillImportError):
            extract_zip_bytes(buf.getvalue())

    def test_find_skill_markdown(self) -> None:
        data = _make_zip({"SKILL.md": "# hi", "ref.md": "r"})
        files = extract_zip_bytes(data)
        key, payload = find_skill_markdown(files)
        self.assertEqual(key, "SKILL.md")
        self.assertEqual(payload.decode(), "# hi")


class TestDiskSkillPackageStore(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        settings = SkillSettings(cache_dir=Path(self._tmp.name))
        self.store = DiskSkillPackageStore(settings)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_install_and_read(self) -> None:
        package = self.store.install_package(
            skill_id="demo-skill",
            skill_md_text="---\nname: demo\ndescription: summary\n---\n# Body",
            resource_files={"REFERENCE.md": b"ref text"},
            source_url="https://example.com/skill.zip",
        )
        self.assertEqual(package.name, "demo")
        self.assertEqual(package.resource_paths, ("REFERENCE.md",))
        loaded = self.store.get("demo-skill")
        self.assertIn("# Body", loaded.content)
        self.assertEqual(self.store.read_resource("demo-skill", "REFERENCE.md"), "ref text")

    def test_get_missing_raises(self) -> None:
        with self.assertRaises(SkillNotFoundError):
            self.store.get("missing")


class TestActivationScope(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_most_recent(self) -> None:
        with activated_skills_scope(()):
            register_activated("a", "Alpha")
            register_activated("b", "Beta")
            resolved = resolve_skill_for_exec(None)
            self.assertEqual(resolved.skill_id, "b")


class TestSkillTools(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        settings = SkillSettings(cache_dir=Path(self._tmp.name))
        self.store = DiskSkillPackageStore(settings)
        self.importer = HttpSkillImporter(store=self.store, settings=settings)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_import_from_market_mock(self) -> None:
        zip_bytes = _make_zip(
            {
                "SKILL.md": "---\nname: pdf\ndescription: pdf ops\n---\nUse reportlab",
                "REFERENCE.md": "# ref",
            }
        )
        self.importer._market.download_zip = AsyncMock(return_value=zip_bytes)  # type: ignore[method-assign]
        self.importer._market.fetch_detail = AsyncMock(return_value={"version": "1.0.0"})  # type: ignore[method-assign]
        tool = SkillImportTool(self.importer)
        obs = await tool.execute({"identifier": "anthropics-skills-pdf"})
        self.assertTrue(obs.success)
        self.assertEqual(obs.payload["skill_id"], "anthropics-skills-pdf")

    async def test_activate_and_read_reference(self) -> None:
        self.store.install_package(
            skill_id="demo",
            skill_md_text="---\nname: demo\ndescription: d\n---\nDo work",
            resource_files={"tips.md": b"tip"},
            source_url="u",
        )
        activate = SkillActivateTool(self.store)
        act_obs = await activate.execute({"skill_id": "demo"})
        self.assertTrue(act_obs.success)
        self.assertIn("Do work", act_obs.payload["text"])

        read_tool = SkillReadReferenceTool(self.store)
        read_obs = await read_tool.execute({"skill_id": "demo", "path": "tips.md"})
        self.assertTrue(read_obs.success)
        self.assertEqual(read_obs.payload["text"], "tip")

    async def test_search_local_fallback(self) -> None:
        self.store.install_package(
            skill_id="pdf-helper",
            skill_md_text="---\nname: pdf\ndescription: make pdf\n---\nbody",
            resource_files={},
            source_url="u",
        )
        tool = SkillSearchTool(self.importer)
        with patch.object(
            self.importer._market,
            "search",
            AsyncMock(side_effect=SkillImportError("no token")),
        ):
            obs = await tool.execute({"query": "pdf"})
        self.assertTrue(obs.success)
        self.assertIn("pdf-helper", obs.payload["text"])


class TestMarketAuth(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        clear_market_token_cache()

    def test_client_assertion_shape(self) -> None:
        endpoint = token_endpoint_for("https://market.lobehub.com")
        self.assertEqual(endpoint, "https://market.lobehub.com/oauth/token")
        secret = "secret"  # noqa: S105 — fixture only
        jwt = create_client_assertion(
            client_id="cid",
            client_secret=secret,
            token_endpoint=endpoint,
            now=1_700_000_000,
        )
        parts = jwt.split(".")
        self.assertEqual(len(parts), 3)
        # re-sign and verify HMAC matches
        import base64
        import hashlib
        import hmac
        import json

        def pad(seg: str) -> bytes:
            return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))

        header = json.loads(pad(parts[0]))
        payload = json.loads(pad(parts[1]))
        self.assertEqual(header["alg"], "HS256")
        self.assertEqual(payload["iss"], "cid")
        self.assertEqual(payload["aud"], endpoint)
        expected = hmac.new(
            secret.encode("utf-8"),
            f"{parts[0]}.{parts[1]}".encode("ascii"),
            hashlib.sha256,
        ).digest()
        self.assertEqual(pad(parts[2]), expected)

    def test_resolve_m2m_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credentials.json"
            path.write_text(
                json.dumps(
                    {
                        "clientId": "file-id",
                        "clientSecret": "file-secret",
                        "baseUrl": "https://market.example.com",
                    }
                ),
                encoding="utf-8",
            )
            settings = SkillSettings(
                market_token=None,
                market_client_id=None,
                market_client_secret=None,
                market_credentials_path=path,
            )
            resolved = resolve_m2m_credentials(settings)
            self.assertIsNotNone(resolved)
            assert resolved is not None
            self.assertEqual(resolved[0], "file-id")
            self.assertEqual(resolved[1], "file-secret")
            self.assertEqual(resolved[2], "https://market.example.com")

    async def test_static_token_preferred(self) -> None:
        static = "static-bearer"
        settings = SkillSettings(market_token=static)
        token = await resolve_market_access_token(settings)
        self.assertEqual(token, static)


class TestDefaultTools(unittest.TestCase):
    def test_build_default_tools_includes_skill_tools(self) -> None:
        with patch("lca.layer0_infra.tools.default_set.resolve_sandbox", return_value=None):
            names = {t.name for t in build_default_tools()}
        self.assertIn("write_file", names)
        self.assertIn("search_skill", names)
        self.assertIn("import_skill", names)
        self.assertIn("activate_skill", names)
        self.assertIn("read_skill_reference", names)
        self.assertNotIn("run_skill_script", names)
        self.assertNotIn("sandbox_execute", names)
        self.assertNotIn("sandbox_inspect", names)

    def test_build_default_tools_includes_run_skill_script_when_sandbox(self) -> None:
        with patch("lca.layer0_infra.tools.default_set.resolve_sandbox") as mock_sbx:
            mock_sbx.return_value = object()
            names = {t.name for t in build_default_tools()}
        self.assertIn("run_skill_script", names)
        self.assertNotIn("sandbox_execute", names)

    def test_sanitize_skill_id(self) -> None:
        self.assertEqual(sanitize_skill_id("anthropics-skills-pdf"), "anthropics-skills-pdf")
        self.assertEqual(sanitize_skill_id("foo/bar"), "foo-bar")


if __name__ == "__main__":
    unittest.main()
