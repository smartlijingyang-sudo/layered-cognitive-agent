"""ADR-0174 §D3 loop_cursor bundle 静态门禁脚本测试。

本测试保证 ``scripts/check_loop_cursor_bundle_required.py`` 在当前仓库
状态下行为正确:

- 迁移完成的 3 个 profile(web-standard / oii-debug / benchmark)必须通过 +
  3 个 loop_cursor.spine_* bundle 必须 provides loop_cursor_factory
- 旧名 ``spine-default.yaml`` / ``spine-benchmark-minimal.yaml`` /
  ``spine-oii-debug.yaml``(legacy)必须 = 0 命中
- warning 与 strict 模式行为分离
- 子命令 ``--strict`` / env ``LOOP_CURSOR_BUNDLE_REQUIRED_STRICT`` 控制

本测试**静态调用 gate 脚本**(不重新实现校验逻辑);所以 gate 脚本修了
错误规则会自然触发相应 test 失败。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_SCRIPT = REPO_ROOT / "scripts" / "check_loop_cursor_bundle_required.py"
PROFILES_DIR = REPO_ROOT / "profiles"
BUNDLES_DIR = REPO_ROOT / "bundles"


def _run_gate(
    *, strict: bool = False, env_strict: bool = False
) -> subprocess.CompletedProcess[str]:
    """运行 gate 脚本。strict 与 env_strict 二选一控制退出码。"""
    cmd = [sys.executable, str(GATE_SCRIPT)]
    if strict:
        cmd.append("--strict")
    env = os.environ.copy()
    if env_strict:
        env["LOOP_CURSOR_BUNDLE_REQUIRED_STRICT"] = "1"
    else:
        env.pop("LOOP_CURSOR_BUNDLE_REQUIRED_STRICT", None)
    return subprocess.run(  # noqa: S603 — trusted local script
        cmd,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
        env=env,
    )


# ── gate 脚本存在 + 可 import 必需的 helper functions ──────────────────


def test_gate_script_exists() -> None:
    """``scripts/check_loop_cursor_bundle_required.py`` 存在。"""
    assert GATE_SCRIPT.exists(), f"missing gate script: {GATE_SCRIPT}"


# ── warning-only 模式(PR-7.1/7.2 当前阶段)───────────────────────────


def test_default_mode_exit_zero_when_only_some_profiles_migrated() -> None:
    """默认模式(warning-only)在分批迁移过渡阶段必须 exit 0。

    PR-7.1/7.2 阶段只迁 oii-debug / benchmark / web-standard 三条;
    余下 7 个 profile 仍缺 loop_cursor.spine_* 引用——这是预期的
    中间态,warning 模式不应阻塞 CI。
    """
    result = _run_gate(strict=False)
    assert result.returncode == 0, (
        f"warning-only mode unexpectedly exited {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_default_mode_emits_warnings_for_unmigrated_profiles() -> None:
    """默认模式对未迁移的 profile 应打印 WARN 行(可读 visibility)。"""
    result = _run_gate(strict=False)
    assert "WARN:" in result.stdout, (
        "warning-only mode should still emit WARN lines for unmigrated profiles\n"
        f"stdout:\n{result.stdout}"
    )


def test_default_mode_passes_for_migrated_profiles() -> None:
    """默认模式 PASS 标注必须包含 oii-debug / benchmark / web-standard。"""
    result = _run_gate(strict=False)
    for migrated in ("oii-debug", "benchmark", "web-standard"):
        assert migrated in result.stdout, (
            f"expected migrated profile mention: {migrated}\nstdout:\n{result.stdout}"
        )


# ── strict 模式(PR-7.x 批次.4 第 4 批目标)───────────────────────────


def test_strict_mode_exit_nonzero_when_some_profiles_unmigrated() -> None:
    """strict 模式 + 未迁移 profile 必须 exit 1。"""
    result = _run_gate(strict=True)
    assert result.returncode != 0, (
        f"strict mode should exit non-zero when unmigrated profiles exist\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_strict_mode_emits_fail_lines_not_just_warnings() -> None:
    """strict 模式必须用 FAIL: 前缀,不只是 WARN。"""
    result = _run_gate(strict=True)
    assert "FAIL:" in result.stdout, f"strict mode should emit FAIL lines, got:\n{result.stdout}"


def test_env_var_strict_mode_works() -> None:
    """``LOOP_CURSOR_BUNDLE_REQUIRED_STRICT=1`` 触发 strict 行为。"""
    result = _run_gate(env_strict=True)
    assert result.returncode != 0, (
        f"env-strict mode should exit non-zero\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ── bundle kind 校验 ───────────────────────────────────────────────


def test_bundles_have_kind_loop_cursor_bundle() -> None:
    """每个 ``bundles/loop_cursor.spine_*.yaml`` 必含 ``kind: loop_cursor_bundle``。"""
    cursor_bundles = sorted(BUNDLES_DIR.glob("loop_cursor.spine_*.yaml"))
    assert cursor_bundles, "expected at least one loop_cursor.spine_*.yaml bundle"
    for bundle in cursor_bundles:
        raw = yaml.safe_load(bundle.read_text(encoding="utf-8"))
        assert isinstance(raw, dict)
        assert raw.get("kind") == "loop_cursor_bundle", (
            f"{bundle.name} 缺顶层 kind: loop_cursor_bundle 字段(ADR-0174 §D2)"
        )


def test_bundles_provide_loop_cursor_factory() -> None:
    """每个 ``loop_cursor.spine_*.yaml`` 顶层 ``provides`` 必含 ``loop_cursor_factory``。"""
    cursor_bundles = sorted(BUNDLES_DIR.glob("loop_cursor.spine_*.yaml"))
    for bundle in cursor_bundles:
        raw = yaml.safe_load(bundle.read_text(encoding="utf-8"))
        provides = raw.get("provides") or []
        assert isinstance(provides, list)
        assert "loop_cursor_factory" in provides, (
            f"{bundle.name} 缺 provides: [..., 'loop_cursor_factory', ...](ADR-0174 §D2)"
        )


# ── legacy 文件名 = 0(ADR-0174 §I-PROF-4)──────────────────────────


def test_legacy_spine_bundles_do_not_exist() -> None:
    """仓库内不存在旧名 ``spine-default.yaml`` 等 3 个 legacy 文件(ADR-0174 §I-PROF-4)。

    PR-7.1/7.2 第 1 批:重命名完成;若 git mv 留有重名遗留,即视为回归。
    """
    for legacy in ("spine-default.yaml", "spine-benchmark-minimal.yaml", "spine-oii-debug.yaml"):
        legacy_path = BUNDLES_DIR / legacy
        assert not legacy_path.exists(), f"legacy bundle 不应存在:{legacy_path}(ADR-0174 §I-PROF-4)"


def test_legacy_spine_bundles_not_referenced_in_profiles() -> None:
    """profile.yaml 不直引用 legacy ``bundles/spine-*.yaml``(ADR-0174 §I-PROF-4)。

    跨 profile grep = 0 hits。
    """
    pattern = re.compile(r"^bundles/spine-[a-z0-9_-]+\.yaml$")
    offenders: list[str] = []
    for profile in sorted(PROFILES_DIR.glob("*.yaml")):
        text = profile.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(profile.name)
    assert not offenders, f"profiles 直引用 legacy bundles/spine-*.yaml: {offenders}"


# ── I-PROF-1:必备 loop_cursor.spine_* 引用 ────────────────────────


def test_migrated_profiles_reference_loop_cursor_spine_bundle() -> None:
    """三个迁移完成的 profile 必含 loop_cursor.spine_* 引用(ADR-0174 §I-PROF-1)。"""
    raw_web = yaml.safe_load((PROFILES_DIR / "web-standard.yaml").read_text(encoding="utf-8"))
    raw_oii = yaml.safe_load((PROFILES_DIR / "oii-debug.yaml").read_text(encoding="utf-8"))
    raw_bench = yaml.safe_load((PROFILES_DIR / "benchmark.yaml").read_text(encoding="utf-8"))
    for name, raw in (
        ("web-standard", raw_web),
        ("oii-debug", raw_oii),
        ("benchmark", raw_bench),
    ):
        bundles = raw.get("bundles") or []
        assert any(
            isinstance(b, str)
            and (b.startswith("loop_cursor.spine_") or b.startswith("bundles/loop_cursor.spine_"))
            for b in bundles
        ), f"{name}.yaml 缺 loop_cursor.spine_* 引用(ADR-0174 §I-PROF-1)"


# ── 子进程边界条件 ──────────────────────────────────────────────


def test_gate_subprocess_runs_successfully_with_clean_state() -> None:
    """端到端 smoke:运行 gate 在正常模式下 exit 0。"""
    result = _run_gate(strict=False)
    assert result.returncode == 0
    assert "OK" in result.stdout or "PASS" in result.stdout or "WARN" in result.stdout
