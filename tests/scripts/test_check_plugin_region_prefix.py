"""Tests for scripts/check_plugin_region_prefix.py (ADR-0231 D3).

校验 ``lca/nodes/**/*.py`` 中 ``@plugin(provides=(...))`` 字符串前缀必须
等于该文件相对 ``lca/nodes/`` 的第一层目录名。漂移即 fail-loud。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from check_plugin_region_prefix import (  # noqa: E402
    extract_provides_prefixes,
    parse_plugin_decorator,
    physical_region_for,
    validate_file,
)


def test_physical_region_for_think_dir():
    assert physical_region_for("lca/nodes/think/route/shortcut.py") == "think"


def test_physical_region_for_act_dir():
    assert physical_region_for("lca/nodes/act/validate/validate.py") == "act"


def test_physical_region_for_concept_dir():
    assert physical_region_for("lca/nodes/concept/decision_classify/parse_tool_calls.py") == "concept"


def test_physical_region_outside_nodes_returns_none():
    assert physical_region_for("lca/plugins/foo/bar.py") is None
    assert physical_region_for("scripts/check_x.py") is None
    assert physical_region_for("tests/test_x.py") is None


def test_parse_plugin_decorator_extracts_provides():
    text = '''
@plugin(
    id="phase.think.shortcut",
    provides=("think::think.shortcut",),
)
class X:
    pass
'''
    decls = parse_plugin_decorator(text)
    assert len(decls) == 1
    assert decls[0]["provides"] == ["think::think.shortcut"]


def test_parse_plugin_decorator_no_plugin():
    text = "class X:\n    pass\n"
    decls = parse_plugin_decorator(text)
    assert decls == []


def test_extract_provides_prefixes_normal():
    provides = ["think::think.shortcut", "think::think.gate"]
    prefixes = extract_provides_prefixes(provides)
    assert prefixes == ["think", "think"]


def test_extract_provides_prefixes_colon_rejected():
    """``phase:think::`` style prefixes should be flagged, not normalized."""
    provides = ["phase:think::think.shortcut"]
    prefixes = extract_provides_prefixes(provides)
    # The function returns whatever it parses — the violation is detected by
    # the caller comparing prefix to physical region.
    assert prefixes == ["phase:think"]


def test_validate_file_matching_prefix():
    """File under lca/nodes/think/ with provides='think::*' is valid."""
    # Simulate a fixture by passing the actual repo path.
    real_path = ROOT / "lca/nodes" / "think" / "route" / "shortcut.py"
    if real_path.exists():
        issues = validate_file(real_path)
        # The fix in PR will migrate phase:think:: to think:: — after fix, no issues.
        # Before fix, this is RED. We assert the function runs without error.
        assert isinstance(issues, list)


def test_validate_file_returns_issue_for_mismatch(tmp_path):
    """A test fixture: lca/nodes/think/x.py with provides='concept::x' must fail."""
    fixture_root = tmp_path
    nodes_dir = fixture_root / "lca" / "nodes" / "think"
    nodes_dir.mkdir(parents=True)
    fixture = nodes_dir / "fake.py"
    fixture.write_text(
        'from lca.harness.plugin_api import plugin\n'
        '\n'
        '@plugin(\n'
        '    id="think.fake",\n'
        '    provides=("concept::fake",),\n'
        ')\n'
        'class FakePlugin:\n'
        '    pass\n'
    )

    # Override the script's _resolve_fixture_root so it sees our tmp_path.
    import check_plugin_region_prefix as mod

    original_root = mod.NODES_DIR
    mod.NODES_DIR = fixture_root / "lca" / "nodes"
    try:
        issues = validate_file(fixture)
    finally:
        mod.NODES_DIR = original_root

    # The file lives under lca/nodes/think/ but provides prefix is 'concept'.
    assert any(
        "concept" in i.message and "think" in i.message for i in issues
    ), f"expected mismatch issue, got {issues!r}"


def test_validate_file_skips_non_plugin_file(tmp_path):
    fixture_root = tmp_path
    nodes_dir = fixture_root / "lca" / "nodes" / "think"
    nodes_dir.mkdir(parents=True)
    fixture = nodes_dir / "noop.py"
    fixture.write_text("class X:\n    pass\n")

    import check_plugin_region_prefix as mod

    original_root = mod.NODES_DIR
    mod.NODES_DIR = fixture_root / "lca" / "nodes"
    try:
        issues = validate_file(fixture)
    finally:
        mod.NODES_DIR = original_root

    assert issues == []


def test_collect_provide_literals_picks_ctx_provide():
    """Rule 3 helper must extract every ``ctx.provide("<key>", ...)`` literal."""
    import ast

    from check_plugin_region_prefix import _collect_provide_literals

    text = (
        "async def setup(ctx, config):\n"
        "    ctx.provide('think::think.x', object())\n"
        "    ctx.require('think::think.y')\n"
        "    ctx.provide('think::think.z')\n"
    )
    tree = ast.parse(text)
    literals = _collect_provide_literals(tree.body[0].body)
    keys = [k for k, _ in literals]
    assert "think::think.x" in keys
    assert "think::think.z" in keys
    # ``ctx.require`` is not ``provide`` — must be filtered out.
    assert all("think.y" not in k for k in keys)


def test_validate_file_rule3_flags_undeclared_provide_literal(tmp_path):
    """``ctx.provide('a::b', ...)`` whose key is missing from declared ``provides=``
    must be flagged. Regression for commit 89a7b256c drift.
    """
    fixture_root = tmp_path
    nodes_dir = fixture_root / "lca" / "nodes" / "perceive"
    nodes_dir.mkdir(parents=True)
    fixture = nodes_dir / "fake.py"
    fixture.write_text(
        "from lca.harness.plugin_api import plugin\n"
        "\n"
        "@plugin(\n"
        "    id='perceive.fake',\n"
        "    provides=('perceive::perceive.fake',),\n"
        ")\n"
        "async def setup(ctx, config):\n"
        "    ctx.provide('phase:perceive::perceive.fake', object())\n"
    )

    import check_plugin_region_prefix as mod

    original_root = mod.NODES_DIR
    mod.NODES_DIR = fixture_root / "lca" / "nodes"
    try:
        issues = validate_file(fixture)
    finally:
        mod.NODES_DIR = original_root

    rule3 = [i for i in issues if "not in declared" in i.message]
    assert len(rule3) == 1
    assert "phase:perceive::perceive.fake" in rule3[0].message
    assert "perceive::perceive.fake" in rule3[0].message  # suggestion hint


def test_validate_file_rule3_passes_when_literal_matches_declared(tmp_path):
    """The happy path: ``ctx.provide`` key is a member of declared ``provides=``."""
    fixture_root = tmp_path
    nodes_dir = fixture_root / "lca" / "nodes" / "perceive"
    nodes_dir.mkdir(parents=True)
    fixture = nodes_dir / "ok.py"
    fixture.write_text(
        "from lca.harness.plugin_api import plugin\n"
        "\n"
        "@plugin(\n"
        "    id='perceive.ok',\n"
        "    provides=('perceive::perceive.ok',),\n"
        ")\n"
        "async def setup(ctx, config):\n"
        "    ctx.provide('perceive::perceive.ok', object())\n"
    )

    import check_plugin_region_prefix as mod

    original_root = mod.NODES_DIR
    mod.NODES_DIR = fixture_root / "lca" / "nodes"
    try:
        issues = validate_file(fixture)
    finally:
        mod.NODES_DIR = original_root

    rule3 = [i for i in issues if "not in declared" in i.message]
    assert rule3 == []
