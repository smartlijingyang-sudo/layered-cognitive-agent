"""lca-ops lobehub ensure 必须真实 apply pnpm patchedDependencies 到 bun-installed node_modules。

背景:LobeHub 上游声明 pnpm-workspace.yaml patchedDependencies(@upstash/qstash),
但 LCA 用 bun install(无 lockfile),bun 不读 pnpm-workspace.yaml → patch 永远不 apply。
lca-ops 之前的 "patches up-to-date" 状态基于 .lca-patched marker 文件(只覆盖 LCA 自有
deploy/lobehub/patches),会掩盖 pnpm-style patch 的真实问题。

测试目标:_ensure_pnpm_patches 必须真正 apply pnpm patches 到 bun-installed
node_modules,即使 LCA 没切回 pnpm。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from lca.infrastructure.cli.config import KernelServeConfig, LobeHubConfig
from lca.infrastructure.cli.services.lobehub import LobeHubService
from lca.infrastructure.cli.state import StateStore


@pytest.fixture
def lobehub_svc(tmp_path: Path) -> LobeHubService:
    root = tmp_path / "repo"
    ui_dir = root / "lobehub-ui"
    ui_dir.mkdir(parents=True)
    (ui_dir / "package.json").write_text(
        '{"version": "2.2.13", "pnpm": {"patchedDependencies": '
        '{"@upstash/foo": "patches/@upstash__foo.patch"}}}'
    )
    # 模拟 bun 安装的 chunk 文件(无 patch 内容)
    bun_pkg = (
        ui_dir
        / "node_modules"
        / ".bun"
        / "@upstash+foo@1.0.0"
        / "node_modules"
        / "@upstash"
        / "foo"
    )
    bun_pkg.mkdir(parents=True)
    (bun_pkg / "chunk-CONTENT.mjs").write_text("// original content\n")

    # 模拟 pnpm-workspace.yaml 风格的 patch 文件(指向 pnpm-style 路径)
    pnpm_patch = ui_dir / "patches" / "@upstash__foo.patch"
    pnpm_patch.parent.mkdir(parents=True)
    pnpm_patch.write_text(
        "diff --git a/chunk-CONTENT.mjs b/chunk-CONTENT.mjs\n"
        "--- a/chunk-CONTENT.mjs\n"
        "+++ b/chunk-CONTENT.mjs\n"
        "@@ -1,1 +1,2 @@\n"
        " // original content\n"
        "+// patched by LCA\n"
    )

    # 创建 deploy/lobehub/patches/ 占位 (避免 _ensure_patches 报缺)
    deploy_patches = root / "deploy" / "lobehub" / "patches"
    deploy_patches.mkdir(parents=True)

    state_dir = tmp_path / "state"
    StateStore(state_dir).save_snapshot("patches", [root / "deploy" / "lobehub"], "*")

    svc = LobeHubService(
        LobeHubConfig(dir="lobehub-ui", dev_port=3010),
        KernelServeConfig(port=8765),
        state_dir,
        root,
    )
    return svc


def test_ensure_pnpm_patches_applies_qstash_to_bun_node_modules(
    lobehub_svc: LobeHubService,
) -> None:
    """pnpm patchedDependencies (@upstash/foo) 必须真 apply 到 bun-installed chunk。"""

    worked = lobehub_svc._ensure_pnpm_patches()
    assert worked, "_ensure_pnpm_patches 应当报告应用"

    chunk = (
        lobehub_svc._dir
        / "node_modules"
        / ".bun"
        / "@upstash+foo@1.0.0"
        / "node_modules"
        / "@upstash"
        / "foo"
        / "chunk-CONTENT.mjs"
    )
    content = chunk.read_text()
    assert "// patched by LCA" in content, f"patch 未真应用: chunk 内容仍是 {content!r}"


def test_ensure_pnpm_patches_no_op_when_package_json_lacks_patched_dependencies(
    tmp_path: Path,
) -> None:
    """package.json 无 patchedDependencies 时,_ensure_pnpm_patches 是 no-op。"""

    root = tmp_path / "repo"
    ui_dir = root / "lobehub-ui"
    ui_dir.mkdir(parents=True)
    (ui_dir / "package.json").write_text('{"version": "2.2.13"}')
    (ui_dir / "patches").mkdir(parents=True)

    state_dir = tmp_path / "state"
    svc = LobeHubService(
        LobeHubConfig(dir="lobehub-ui", dev_port=3010),
        KernelServeConfig(port=8765),
        state_dir,
        root,
    )

    worked = svc._ensure_pnpm_patches()
    assert worked is False, "无 patchedDependencies 时,_ensure_pnpm_patches 应返回 False"


def test_ensure_pnpm_patches_called_within_ensure_ready(lobehub_svc: LobeHubService) -> None:
    """ensure_ready 必须调 _ensure_pnpm_patches(否则 bug 复发)。"""

    seen: list[bool] = []

    def fake_apply(self: LobeHubService) -> bool:
        seen.append(True)
        return True

    with patch.object(
        LobeHubService, "_ensure_pnpm_patches", autospec=True, side_effect=fake_apply
    ):
        lobehub_svc.ensure_ready()

    assert seen, "ensure_ready 未调 _ensure_pnpm_patches;pnpm patch 永远不会被 LCA apply"


def test_ensure_pnpm_patches_returns_false_when_already_applied(
    lobehub_svc: LobeHubService,
) -> None:
    """已 apply 的 patch 不应重复写入(用 sentinel marker 文件)。"""

    # First call applies
    lobehub_svc._ensure_pnpm_patches()

    # Mark as applied via patch sentinel
    state_dir = lobehub_svc._state._dir
    marker = state_dir.parent / ".lca-pnpm-patched"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("ok")

    # Second call returns False (already done)
    worked = lobehub_svc._ensure_pnpm_patches()
    assert worked is False, "_ensure_pnpm_patches 第二次应 no-op(避免重复写入)"


def test_ensure_pnpm_patches_records_failure_when_chunk_hash_stale(
    tmp_path: Path,
) -> None:
    """patch 目标 chunk hash 不存在时,不应静默成功;要记录 failure 给运维。

    背景:上游 lobehub 或 @upstash/qstash 重新构建后,chunk hash 变化,
    git apply 会 skip(无 .rej 也无 error),无声成功是 bug — 应当记录 failed
    列表让 lca-ops status 显示 stale patch。
    """

    root = tmp_path / "repo"
    ui_dir = root / "lobehub-ui"
    ui_dir.mkdir(parents=True)
    (ui_dir / "package.json").write_text(
        '{"version": "2.2.13", "pnpm": {"patchedDependencies": '
        '{"@upstash/foo": "patches/@upstash__foo.patch"}}}'
    )

    bun_pkg = (
        ui_dir
        / "node_modules"
        / ".bun"
        / "@upstash+foo@1.0.0"
        / "node_modules"
        / "@upstash"
        / "foo"
    )
    bun_pkg.mkdir(parents=True)
    # 关键:内容 + 文件名 都跟 patch 不匹配(patch 想改 chunk-T3Z5YUS4)
    (bun_pkg / "chunk-DIFFERENT.mjs").write_text("// different content\n")

    pnpm_patch = ui_dir / "patches" / "@upstash__foo.patch"
    pnpm_patch.parent.mkdir(parents=True)
    pnpm_patch.write_text(
        "diff --git a/chunk-T3Z5YUS4.mjs b/chunk-T3Z5YUS4.mjs\n"
        "--- a/chunk-T3Z5YUS4.mjs\n"
        "+++ b/chunk-T3Z5YUS4.mjs\n"
        "@@ -1,1 +1,2 @@\n"
        " // original\n"
        "+// patched\n"
    )

    deploy_patches = root / "deploy" / "lobehub" / "patches"
    deploy_patches.mkdir(parents=True)

    state_dir = tmp_path / "state"
    svc = LobeHubService(
        LobeHubConfig(dir="lobehub-ui", dev_port=3010),
        KernelServeConfig(port=8765),
        state_dir,
        root,
    )

    worked = svc._ensure_pnpm_patches()
    assert worked is False, "chunk hash 不匹配时必须返回 False,不能静默成功"

    marker = state_dir / "lobehub-pnpm-patches.marker"
    assert marker.exists(), "失败也必须写 marker 记录"
    payload = json.loads(marker.read_text())
    assert payload.get("patched_count") == 0
    assert "failed" in payload
    assert any("git apply failed" in f for f in payload["failed"]), (
        f"failed 列表应含 git apply 失败原因,实际: {payload['failed']}"
    )
