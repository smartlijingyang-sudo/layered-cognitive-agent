"""Behavioral tests for the SinglePluginDoctor pass (PR-0199-P2-09).

Per ADR-0199 §5.1 the single-plugin doctor is a pure AST scan of one
plugin file: no import, no setup() invocation, no K3 boot (I-HPC-7),
no journal writes. These tests assert:
  * DOC-PS-001 missing effects / DOC-PS-007 plugin in __init__.py /
    DOC-PS-002 dual manifest detection via AST only;
  * DOC-PS-101 (no @plugin decorator) is INFO, not error;
  * DOC-PS-102 unknown effect prefixes are WARNING;
  * DOC-PS-901/902 are doctor-internal (file-not-found, syntax error);
  * multiple @plugin decorators in one file are each audited;
  * async functions with @plugin are also audited;
  * subject is str(plugin_path);
  * determinism (C8): same input → same findings.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import pytest

from lca.contracts.diagnostics.doctor import DoctorFinding
from lca.harness.diagnostics.doctor import SinglePluginDoctor

# Stable machine-code regex copied verbatim from
# lca.contracts.diagnostics.doctor (DOC-<DOMAIN>-<NNN>).
_CODE_RE = re.compile(r"^DOC-[A-Z]{2,6}-\d{3,}$")


# ─────────── helpers ───────────


def _write_plugin(path: Path, source: str) -> Path:
    """Write a Python source file with the plugin source under test."""
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


def _make_clean_plugin(
    path: Path,
    *,
    plugin_id: str = "lca.plugins.example.example",
    effects: str = "('journal.append',)",
) -> Path:
    """A clean @plugin declaration that should produce zero findings."""
    return _write_plugin(
        path,
        f"""
        from lca.harness.plugin.declaration import plugin

        @plugin(
            id={plugin_id!r},
            layer='L1',
            kind='provider',
            effects={effects},
        )
        def setup(ctx):
            return None
        """,
    )


# ─────────── FileNotFound / SyntaxError ───────────


class TestDoctorInternalFailures:
    """DOC-PS-901/902 are reserved for doctor-internal issues."""

    def test_nonexistent_path_emits_doc_ps_901(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.py"
        doctor = SinglePluginDoctor()
        report = doctor.run(missing)
        assert report.subject == str(missing)
        assert len(report.findings) == 1
        finding = report.findings[0]
        assert finding.code == "DOC-PS-901"
        assert finding.severity == "error"
        assert finding.owner == "ADR-0199"
        assert "not found" in finding.message

    def test_syntax_error_emits_doc_ps_902(self, tmp_path: Path) -> None:
        bad = tmp_path / "broken.py"
        bad.write_text("def setup(:\n    pass\n", encoding="utf-8")
        doctor = SinglePluginDoctor()
        report = doctor.run(bad)
        assert report.subject == str(bad)
        assert len(report.findings) == 1
        finding = report.findings[0]
        assert finding.code == "DOC-PS-902"
        assert finding.severity == "error"
        assert finding.owner == "ADR-0199"
        assert "syntax error" in finding.message

    def test_constructor_stores_plugin_path(self, tmp_path: Path) -> None:
        candidate = _make_clean_plugin(tmp_path / "candidate.py")
        doctor = SinglePluginDoctor(plugin_path=candidate)
        # Stored plugin_path is informational; run() still accepts the
        # explicit path argument and audits it normally.
        report = doctor.run(candidate)
        assert report.summary.errors == 0
        assert report.findings == ()


# ─────────── CleanPlugin ───────────


class TestCleanPlugin:
    """A well-formed plugin should produce zero findings."""

    def test_clean_plugin_no_findings(self, tmp_path: Path) -> None:
        plugin = _make_clean_plugin(tmp_path / "ok.py")
        doctor = SinglePluginDoctor()
        report = doctor.run(plugin)
        assert report.findings == ()
        assert report.summary.total == 0
        assert report.summary.errors == 0
        assert report.summary.warnings == 0
        assert report.summary.info == 0
        assert report.has_errors() is False

    def test_subject_is_stringified_plugin_path(self, tmp_path: Path) -> None:
        plugin = _make_clean_plugin(tmp_path / "ok.py")
        doctor = SinglePluginDoctor()
        report = doctor.run(plugin)
        assert report.subject == str(plugin)
        assert report.activation_ref is None

    def test_clean_plugin_uses_constructor_path(self, tmp_path: Path) -> None:
        plugin = _make_clean_plugin(tmp_path / "ok.py")
        doctor = SinglePluginDoctor(plugin_path=plugin)
        # Stored plugin_path is informational; explicit run() argument wins.
        report = doctor.run(plugin)
        assert report.findings == ()


# ─────────── MissingEffects ───────────


class TestMissingEffects:
    """@plugin(...) missing effects= emits DOC-PS-001."""

    def test_missing_effects_emits_doc_ps_001(self, tmp_path: Path) -> None:
        plugin = _write_plugin(
            tmp_path / "no_effects.py",
            """
            from lca.harness.plugin.declaration import plugin

            @plugin(
                id='lca.plugins.foo.foo',
                layer='L1',
                kind='provider',
            )
            def setup(ctx):
                return None
            """,
        )
        doctor = SinglePluginDoctor()
        report = doctor.run(plugin)
        codes = [f.code for f in report.findings]
        assert "DOC-PS-001" in codes
        finding = next(f for f in report.findings if f.code == "DOC-PS-001")
        assert finding.severity == "error"
        assert finding.owner == "ADR-0199"
        assert finding.message  # non-empty
        assert finding.remediation  # non-empty

    def test_missing_effects_lists_plugin_id(self, tmp_path: Path) -> None:
        plugin = _write_plugin(
            tmp_path / "with_id.py",
            """
            from lca.harness.plugin.declaration import plugin

            @plugin(
                id='lca.plugins.named.named',
                layer='L1',
                kind='provider',
            )
            def setup(ctx):
                return None
            """,
        )
        doctor = SinglePluginDoctor()
        report = doctor.run(plugin)
        finding = next(f for f in report.findings if f.code == "DOC-PS-001")
        assert finding.plugin_id == "lca.plugins.named.named"

    def test_missing_effects_without_id_has_none_plugin_id(self, tmp_path: Path) -> None:
        plugin = _write_plugin(
            tmp_path / "no_id.py",
            """
            from lca.harness.plugin.declaration import plugin

            @plugin(
                layer='L1',
                kind='provider',
            )
            def setup(ctx):
                return None
            """,
        )
        doctor = SinglePluginDoctor()
        report = doctor.run(plugin)
        finding = next(f for f in report.findings if f.code == "DOC-PS-001")
        assert finding.plugin_id is None


# ─────────── KnownEffects ───────────


class TestKnownEffects:
    """Recognized effect prefixes are accepted without warning."""

    def test_known_effect_prefix_accepted(self, tmp_path: Path) -> None:
        plugin = _make_clean_plugin(
            tmp_path / "journal.py",
            plugin_id="lca.plugins.journal.writer",
            effects="('journal.append',)",
        )
        doctor = SinglePluginDoctor()
        report = doctor.run(plugin)
        # No DOC-PS-102 expected for known prefixes.
        assert all(f.code != "DOC-PS-102" for f in report.findings)

    @pytest.mark.parametrize(
        "effects_literal",
        [
            "('journal.append',)",
            "('state.read', 'state.write',)",
            "('memory.semantic',)",
            "('tools.shell',)",
            "('policy.audit',)",
        ],
    )
    def test_each_known_prefix_accepted(self, tmp_path: Path, effects_literal: str) -> None:
        plugin = _make_clean_plugin(tmp_path / "ok.py", effects=effects_literal)
        doctor = SinglePluginDoctor()
        report = doctor.run(plugin)
        assert report.findings == ()


# ─────────── UnknownEffects ───────────


class TestUnknownEffects:
    """Unknown effect prefixes emit DOC-PS-102 (warning, not error)."""

    def test_unknown_effect_prefix_emits_doc_ps_102(self, tmp_path: Path) -> None:
        plugin = _write_plugin(
            tmp_path / "weird.py",
            """
            from lca.harness.plugin.declaration import plugin

            @plugin(
                id='lca.plugins.weird.weird',
                layer='L1',
                kind='provider',
                effects=('custom.made.up',),
            )
            def setup(ctx):
                return None
            """,
        )
        doctor = SinglePluginDoctor()
        report = doctor.run(plugin)
        codes = [f.code for f in report.findings]
        assert "DOC-PS-102" in codes
        finding = next(f for f in report.findings if f.code == "DOC-PS-102")
        assert finding.owner == "ADR-0199"
        assert "custom.made.up" in finding.message

    def test_unknown_effect_is_warning_not_error(self, tmp_path: Path) -> None:
        plugin = _write_plugin(
            tmp_path / "weird.py",
            """
            from lca.harness.plugin.declaration import plugin

            @plugin(
                id='lca.plugins.weird.weird',
                layer='L1',
                kind='provider',
                effects=('unknown.foo',),
            )
            def setup(ctx):
                return None
            """,
        )
        doctor = SinglePluginDoctor()
        report = doctor.run(plugin)
        finding = next(f for f in report.findings if f.code == "DOC-PS-102")
        assert finding.severity == "warning"
        assert report.summary.warnings == 1
        assert report.summary.errors == 0
        assert report.has_errors() is False


# ─────────── PluginInInit ───────────


class TestPluginInInit:
    """@plugin in __init__.py emits DOC-PS-007."""

    def test_plugin_in_init_emits_doc_ps_007(self, tmp_path: Path) -> None:
        package = tmp_path / "pkg"
        package.mkdir()
        init = package / "__init__.py"
        _write_plugin(
            init,
            """
            from lca.harness.plugin.declaration import plugin

            @plugin(
                id='lca.plugins.pkg.pkg',
                layer='L1',
                kind='provider',
                effects=('journal.append',),
            )
            def setup(ctx):
                return None
            """,
        )
        doctor = SinglePluginDoctor()
        report = doctor.run(init)
        codes = [f.code for f in report.findings]
        assert "DOC-PS-007" in codes
        finding = next(f for f in report.findings if f.code == "DOC-PS-007")
        assert finding.severity == "error"
        assert "__init__.py" in finding.message


# ─────────── DualManifest ───────────


class TestDualManifest:
    """event_plugin_spec + plugin_spec together → DOC-PS-002."""

    def test_dual_manifest_emits_doc_ps_002(self, tmp_path: Path) -> None:
        manifest = _write_plugin(
            tmp_path / "manifest.py",
            """
            event_plugin_spec = None
            plugin_spec = {"id": "x"}
            """,
        )
        doctor = SinglePluginDoctor()
        report = doctor.run(manifest)
        codes = [f.code for f in report.findings]
        assert "DOC-PS-002" in codes
        finding = next(f for f in report.findings if f.code == "DOC-PS-002")
        assert finding.severity == "error"
        assert "dual manifest" in finding.message

    def test_only_event_plugin_spec_no_finding(self, tmp_path: Path) -> None:
        manifest = _write_plugin(
            tmp_path / "manifest.py",
            """
            event_plugin_spec = None
            """,
        )
        doctor = SinglePluginDoctor()
        report = doctor.run(manifest)
        assert all(f.code != "DOC-PS-002" for f in report.findings)

    def test_only_plugin_spec_no_finding(self, tmp_path: Path) -> None:
        manifest = _write_plugin(
            tmp_path / "manifest.py",
            """
            plugin_spec = {"id": "x"}
            """,
        )
        doctor = SinglePluginDoctor()
        report = doctor.run(manifest)
        assert all(f.code != "DOC-PS-002" for f in report.findings)


# ─────────── NoPluginDecorator ───────────


class TestNoPluginDecorator:
    """Module without @plugin emits DOC-PS-101 (info)."""

    def test_no_plugin_decorator_emits_doc_ps_101_info(self, tmp_path: Path) -> None:
        plain = _write_plugin(
            tmp_path / "plain.py",
            """
            def setup(ctx):
                return None
            """,
        )
        doctor = SinglePluginDoctor()
        report = doctor.run(plain)
        codes = [f.code for f in report.findings]
        assert "DOC-PS-101" in codes
        finding = next(f for f in report.findings if f.code == "DOC-PS-101")
        assert finding.severity == "info"
        assert report.summary.info == 1
        assert report.summary.errors == 0
        assert report.has_errors() is False


# ─────────── MultiplePlugins ───────────


class TestMultiplePlugins:
    """Each @plugin decorator is audited independently."""

    def test_multiple_plugins_in_one_file_each_audited(self, tmp_path: Path) -> None:
        plugin = _write_plugin(
            tmp_path / "two.py",
            """
            from lca.harness.plugin.declaration import plugin

            @plugin(
                id='lca.plugins.two.first',
                layer='L1',
                kind='provider',
                effects=('journal.append',),
            )
            def first(ctx):
                return None

            @plugin(
                id='lca.plugins.two.second',
                layer='L1',
                kind='provider',
            )
            def second(ctx):
                return None
            """,
        )
        doctor = SinglePluginDoctor()
        report = doctor.run(plugin)
        # First plugin: clean → no findings for it.
        # Second plugin: missing effects → DOC-PS-001.
        missing_effects = [f for f in report.findings if f.code == "DOC-PS-001"]
        assert len(missing_effects) == 1
        assert missing_effects[0].plugin_id == "lca.plugins.two.second"


# ─────────── AsyncFunctionSupport ───────────


class TestAsyncFunctionSupport:
    """Async functions with @plugin are also audited."""

    def test_async_function_with_plugin_also_audited(self, tmp_path: Path) -> None:
        plugin = _write_plugin(
            tmp_path / "async_plugin.py",
            """
            from lca.harness.plugin.declaration import plugin

            @plugin(
                id='lca.plugins.async.async',
                layer='L1',
                kind='provider',
                effects=('journal.append',),
            )
            async def setup(ctx):
                return None
            """,
        )
        doctor = SinglePluginDoctor()
        report = doctor.run(plugin)
        # Clean async plugin → zero findings.
        assert report.findings == ()

    def test_async_function_missing_effects_audited(self, tmp_path: Path) -> None:
        plugin = _write_plugin(
            tmp_path / "async_no_effects.py",
            """
            from lca.harness.plugin.declaration import plugin

            @plugin(
                id='lca.plugins.async.missing',
                layer='L1',
                kind='provider',
            )
            async def setup(ctx):
                return None
            """,
        )
        doctor = SinglePluginDoctor()
        report = doctor.run(plugin)
        codes = [f.code for f in report.findings]
        assert "DOC-PS-001" in codes


# ─────────── ArchitecturalInvariants ───────────


class TestArchitecturalInvariants:
    """Per I-HPC-7: pure AST pass; per C8: deterministic."""

    def test_no_journal_writes_or_k3_boot(self) -> None:
        """Module must not import session / journal / kernel boot paths."""
        import lca.harness.diagnostics.doctor.single_plugin as mod

        source_file = Path(mod.__file__)
        assert source_file.is_file()
        text = source_file.read_text(encoding="utf-8")
        import ast as _ast

        tree = _ast.parse(text)
        imported: list[str] = []
        for node in _ast.walk(tree):
            if isinstance(node, _ast.ImportFrom):
                mod_name = node.module or ""
                if (
                    mod_name.startswith("lca.session")
                    or mod_name.startswith("lca.journal")
                    or mod_name.startswith("lca.kernel")
                    or mod_name.startswith("lca.harness.profile.resolve")
                    or mod_name.startswith("lca.cognition")
                ):
                    imported.append(mod_name)
            elif isinstance(node, _ast.Import):
                for alias in node.names:
                    if (
                        alias.name.startswith("lca.session")
                        or alias.name.startswith("lca.journal")
                        or alias.name.startswith("lca.kernel")
                        or alias.name.startswith("lca.cognition")
                    ):
                        imported.append(alias.name)
        assert imported == [], (
            f"SinglePluginDoctor must NOT import session/journal/kernel (I-HPC-7); got {imported!r}"
        )

    def test_no_setup_invocation(self) -> None:
        """Doctor must not invoke setup() — no `setup(` calls in module source."""
        import lca.harness.diagnostics.doctor.single_plugin as mod

        text = Path(mod.__file__).read_text(encoding="utf-8")
        import ast as _ast

        tree = _ast.parse(text)
        setup_calls: list[tuple[int, str]] = []
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Call):
                func = node.func
                name: str | None = None
                if isinstance(func, _ast.Name):
                    name = func.id
                elif isinstance(func, _ast.Attribute):
                    name = func.attr
                if name == "setup":
                    setup_calls.append((getattr(node, "lineno", 0), name))
        assert setup_calls == [], (
            f"SinglePluginDoctor must not call setup() (I-HPC-7); got {setup_calls!r}"
        )

    def test_only_reads_file_no_other_io(self) -> None:
        """Doctor uses path.exists() + path.read_text() — no other fs APIs."""
        import lca.harness.diagnostics.doctor.single_plugin as mod

        text = Path(mod.__file__).read_text(encoding="utf-8")
        # Must not open / write / unlink / rmtree / rename / replace / mkdir.
        forbidden_apis = (
            "pathlib.Path.write_text",
            "pathlib.Path.unlink",
            "shutil.rmtree",
            "os.remove",
            "os.unlink",
            "open(",  # raw open() — even with mode "r" is too liberal; use Path.read_text
        )
        for forbidden in forbidden_apis:
            assert forbidden not in text, (
                f"SinglePluginDoctor must not call {forbidden!r} (I-HPC-7)"
            )


# ─────────── Determinism ───────────


class TestDeterminism:
    """C8: same input → same findings across calls."""

    def test_same_input_same_findings(self, tmp_path: Path) -> None:
        plugin = _write_plugin(
            tmp_path / "stable.py",
            """
            from lca.harness.plugin.declaration import plugin

            @plugin(
                id='lca.plugins.stable.stable',
                layer='L1',
                kind='provider',
                effects=('journal.append', 'state.write'),
            )
            def setup(ctx):
                return None
            """,
        )
        doctor = SinglePluginDoctor()
        a = doctor.run(plugin)
        b = doctor.run(plugin)
        assert a.to_jsonable() == b.to_jsonable()


# ─────────── DoctorFindingShape ───────────


class TestDoctorFindingShape:
    """All findings satisfy the DoctorFinding contract."""

    def test_every_finding_has_valid_code_shape(self, tmp_path: Path) -> None:
        plugin = _write_plugin(
            tmp_path / "many.py",
            """
            from lca.harness.plugin.declaration import plugin

            event_plugin_spec = None
            plugin_spec = {"id": "x"}

            @plugin(
                id='lca.plugins.many.many',
                layer='L1',
                kind='provider',
                effects=('unknown.thing',),
            )
            def setup(ctx):
                return None
            """,
        )
        doctor = SinglePluginDoctor()
        report = doctor.run(plugin)
        assert report.findings, "expected at least one finding for this pathological plugin"
        for f in report.findings:
            assert isinstance(f, DoctorFinding)
            assert _CODE_RE.match(f.code), f"bad code shape: {f.code!r}"
            assert f.severity in ("error", "warning", "info")
            assert f.owner
            assert f.message
            assert f.remediation
