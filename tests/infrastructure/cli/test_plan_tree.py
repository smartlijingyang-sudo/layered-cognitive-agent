"""CLI integration test for ``lca-ops plan tree`` (观察面诊断命令).

Plan tree recursively inflates ``sub_spec_ref.plan_ref`` so an operator
can see the full declarative phase graph in one view: top-level phases,
think subgraph, and nested subgraphs — without rerunning kernel boots or
grepping compiled plan JSON.

Per AGENTS.md §2.3 (control / observe separation) this command is
read-only — no K3 boot, no journal writes, no network. It depends on
``lca.harness.declarative.compile.subgraph_resolver._load_bundle_graph_spec``
and the canonical ``CompiledRunPlan`` produced by ``plan compile``.

NOTE (round-0422): the former ``profiles/think-subgraph-dev.yaml`` fixture
was intentionally deleted by the repo owner (7d4072d1b, 2026-09-11 —
"single-bundle dev fixture is no longer coherent after P10"; the
production graph family is the single Layer-3 ``agent.run.phase`` graph).
All happy-path tests now run against the factory
``profiles/web-standard.yaml``; failure-path tests patch a *copy* of
``bundles/outer/phase_main.yaml`` (the home of L0 ``think.main``'s
``sub_spec_ref``) and repoint a profile copy at it.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from typer.testing import CliRunner

from lca.infrastructure.cli.commands.profile import declarative as declarative_module

REPO_ROOT = Path(__file__).resolve().parents[3]
WEB_STANDARD_PROFILE = REPO_ROOT / "profiles" / "web-standard.yaml"


def _build_app() -> typer.Typer:
    """Minimal Typer app that wires ``plan tree`` only.

    Importing the full ``lca-ops`` app pulls every command group at
    module load time. Tests focused on ``plan tree`` use a minimal
    app + ``declarative_module.register`` to keep imports tight.
    """
    app = typer.Typer()
    declarative_module.register(app)
    return app


def _make_temp_profile(tmp_path: Path, *, plan_ref: str) -> Path:
    """Compose a web-standard copy whose L0 ``think.main`` points at a fake plan_ref.

    The L0 ``think.main`` node's ``sub_spec_ref`` lives in
    ``bundles/outer/phase_main.yaml`` (not in the profile itself), so both
    files are copied into ``tmp_path``: the bundle copy gets its
    ``plan_ref: bundles/think/think_subgraph.yaml`` rewritten, and the
    profile copy's bundle entry is repointed at the bundle copy. Test
    intent stays on plan tree's subgraph inflate logic rather than
    reproduction of a full profile.
    """
    bundle_src = REPO_ROOT / "bundles" / "outer" / "phase_main.yaml"
    bundle_dst = tmp_path / "phase_main_patched.yaml"
    bundle_dst.write_text(
        bundle_src.read_text().replace(
            "plan_ref: bundles/think/think_subgraph.yaml",
            f"plan_ref: {plan_ref}",
        )
    )
    src = REPO_ROOT / "profiles" / "web-standard.yaml"
    dst = tmp_path / "profile.yaml"
    dst.write_text(
        src.read_text().replace(
            "- bundles/outer/phase_main.yaml",
            f"- {bundle_dst}",
        )
    )
    return dst


# ── Smoke: factory profile ───────────────────────────────────────────


def test_plan_tree_web_standard_profile_text() -> None:
    """Default text mode renders L0 + L1 + L2 with node ids visible (web-standard)."""
    runner = CliRunner()
    app = _build_app()
    result = runner.invoke(app, ["plan", "tree", str(WEB_STANDARD_PROFILE)])

    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    out = result.stdout
    assert "phase_graph[L0]" in out
    assert "think.main" in out
    assert "think.subgraph[L1]" in out
    assert "bundles/think/think_subgraph.yaml" in out
    assert "think.shortcut" in out
    assert "think.route" in out
    assert "think.reason" in out
    assert "think.gate" in out
    # nested L2
    assert "think.reason.subgraph[L2]" in out
    assert "bundles/think_reason.yaml" in out
    assert "think.reason.plan" in out
    assert "think.reason.render" in out
    assert "all layers inflated and validated" in out


def test_plan_tree_web_standard_profile_json_structure() -> None:
    """JSON mode emits top + layers with parent linkage and inflate statuses."""
    runner = CliRunner()
    app = _build_app()
    result = runner.invoke(app, ["plan", "tree", str(WEB_STANDARD_PROFILE), "--json"])

    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    payload = json.loads(result.stdout)

    assert payload["schema_version"] == "v2"
    assert payload["plan_ref"]

    top = payload["top"]
    assert [n["id"] for n in top["nodes"]] == [
        "perceive.main",
        "think.main",
        "act.main",
        "reflect.main",
        "remember.main",
        "terminal.commit",
        "intervene.interrupt",
    ]
    think_top = next(n for n in top["nodes"] if n["id"] == "think.main")
    assert think_top["binding"] is None
    assert think_top["sub_spec_ref"]["plan_ref"] == "bundles/think/think_subgraph.yaml"

    think_layer = next(
        layer for layer in payload["layers"] if layer["parent_node"] == "think.main"
    )
    assert think_layer["plan_ref"] == "bundles/think/think_subgraph.yaml"
    assert think_layer["depth"] == 1
    assert [n["id"] for n in think_layer["nodes"]] == [
        "think.shortcut",
        "think.route.decide",
        "think.budget.gate",
        "think.context.summarize",
        "think.route",
        "think.reason",
        "think.history.assemble",
        "llm.invoke",
        "llm.persist",
        "think.decision.parse",
        "think.decision.repair",
        "think.gate",
    ]
    # nested L2 child of think.reason
    reason_layer = next(
        child
        for child in think_layer["children"]
        if child["plan_ref"] == "bundles/think_reason.yaml"
    )
    assert reason_layer["parent_node"] == "think.reason"
    assert reason_layer["depth"] == 2
    assert [n["id"] for n in reason_layer["nodes"]] == [
        "think.reason.fork_tools",
        "think.reason.plan",
        "think.reason.render",
    ]


# ── Depth control ──────────────────────────────────────────────────────


def test_plan_tree_depth_one_omits_nested_layer() -> None:
    """``--depth 1`` 应只 inflate 顶层 sub_spec_ref,不递归到 think.reason。"""
    runner = CliRunner()
    app = _build_app()
    result = runner.invoke(app, ["plan", "tree", str(WEB_STANDARD_PROFILE), "--depth", "1"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert "think.subgraph[L1]" in result.stdout
    # nested L2 not rendered
    assert "think.reason.subgraph[L2]" not in result.stdout


def test_plan_tree_depth_zero_omits_all_subgraphs() -> None:
    """``--depth 0`` 仅展示顶层 phase_graph,不 inflate 任何 sub_spec_ref。

    顶层 sub_spec_ref 字段(``sub=bundles/think/think_subgraph.yaml`` 标记)仍然打印,因
    为它来自 top phase_graph 节点本身而不是 inflate;但 L1/L2 子图节点
    (think.shortcut / think.reason.plan 等)不应出现。
    """
    runner = CliRunner()
    app = _build_app()
    result = runner.invoke(app, ["plan", "tree", str(WEB_STANDARD_PROFILE), "--depth", "0"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert "phase_graph[L0]" in result.stdout
    assert "think.subgraph[L1]" not in result.stdout
    assert "think.shortcut" not in result.stdout
    assert "think.reason.plan" not in result.stdout


# ── Failure paths ──────────────────────────────────────────────────────


def test_plan_tree_missing_subgraph_file(tmp_path: Path) -> None:
    """sub_spec_ref.plan_ref 指向不存在的 yaml 时,文本 + JSON 都应报错并通过 error marker 失败。"""
    profile = _make_temp_profile(tmp_path, plan_ref="bundles/__does_not_exist__.yaml")
    runner = CliRunner()
    app = _build_app()
    result = runner.invoke(app, ["plan", "tree", str(profile)])
    # Note: the former global ``sys.exit`` stub (tests/conftest.py) was removed
    # (todo-14); ``result.exit_code`` now carries the real CLI exit code.
    # Marker assertions stay as the operator-facing signal.
    assert "not found on disk" in result.stdout
    assert "subgraph layers failed to inflate" in (result.stderr or "")
    assert "✗" in result.stdout

    json_result = runner.invoke(app, ["plan", "tree", str(profile), "--json"])
    # Payload is still emitted with the error marker in the layers list —
    # that is the operator-facing signal (exit codes are real again post todo-14).
    payload = json.loads(json_result.stdout)
    bad_layers = [layer for layer in payload["layers"] if "error" in layer]
    assert len(bad_layers) == 1
    assert "not found on disk" in bad_layers[0]["error"]


def test_plan_tree_broken_subgraph_yaml(tmp_path: Path) -> None:
    """sub_spec_ref.plan_ref 指向有 DTO 校验错误的 yaml(边指向不存在的节点)时,error marker 必须可见。"""
    bad_yaml = tmp_path / "broken.yaml"
    bad_yaml.write_text(
        "id: broken\n"
        "region: phase:test\n"
        "nodes:\n"
        "  - id: a\n"
        "    factory: broken.a\n"
        "edges:\n"
        "  - from: a\n"
        "    to: ghost\n"
    )
    profile = _make_temp_profile(tmp_path, plan_ref=str(bad_yaml))
    runner = CliRunner()
    app = _build_app()
    result = runner.invoke(app, ["plan", "tree", str(profile)])
    assert "inflate failed" in result.stdout
    assert "ghost" in result.stdout  # original DeclarativeValidationError message


# ── Compile failure surfaces verbatim ──────────────────────────────────


def test_plan_tree_propagates_compile_errors(tmp_path: Path) -> None:
    """Profile 无法 resolve/compile 时,plan tree 不假装成功,把错误透传给 operator."""
    profile = tmp_path / "nope.yaml"  # 不存在的文件:resolve 期即 OSError
    runner = CliRunner()
    app = _build_app()
    result = runner.invoke(app, ["plan", "tree", str(profile)])
    assert "plan tree: compile failed" in (result.stderr or "")


def test_plan_tree_empty_plan_fails_loud(tmp_path: Path) -> None:
    """B-088:编译出空顶层图(垃圾内容 profile)时,plan tree 不得打印绿勾假装成功。"""
    profile = tmp_path / "garbage.yaml"
    profile.write_text("this is not a real profile: true\n")
    runner = CliRunner()
    app = _build_app()
    result = runner.invoke(app, ["plan", "tree", str(profile)])
    assert "plan tree: empty plan" in (result.stderr or "")
    assert "all layers inflated and validated" not in (result.stdout or "")


# ── Help text ──────────────────────────────────────────────────────────


def test_plan_tree_help_lists_depth_option() -> None:
    """plan tree --help 必须列出 --depth / --json,与命令文档一致."""
    runner = CliRunner()
    app = _build_app()
    result = runner.invoke(app, ["plan", "tree", "--help"])
    assert result.exit_code == 0
    assert "--depth" in result.stdout
    assert "--json" in result.stdout
