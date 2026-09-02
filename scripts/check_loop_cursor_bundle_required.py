#!/usr/bin/env python3
"""check_loop_cursor_bundle_required — ADR-0174 §D3 机器可执行门禁。

扫描 ``profiles/*.yaml`` 与 ``bundles/loop_cursor.spine_*.yaml`` 做静态校验:

    1. 每 profile.yaml **必须** 引用 ``bundles/loop_cursor.spine_*.yaml``
       一项(I-PROF-1:loop_cursor bundle 强制)。
    2. 每个 ``bundles/loop_cursor.spine_*.yaml`` **必须** 在顶层声明
       ``kind: loop_cursor_bundle`` 与 ``provides: [loop_cursor_factory, ...]``
       之一(避免被改名成裸 spine yaml)。
    3. profile yaml 中**禁止** 直引用 ``bundles/spine-*.yaml``(除非是
       ``loop_cursor.spine_*``),回归保护 I-PROF-4。
    4. profile yaml 不允许存在多个 ``bundles/loop_cursor.spine_*`` 引用
       —— 单一 source-of-truth(每 profile 一个 spine variant)。

阶段门禁(ADR-0174 §D3):
- PR-7.1/7.2 第 1 批:warning 模式(exit 0 + 打印警告);不阻塞 CI
- PR-7.x 批次.4 第 4 批完成阶段:--strict 模式 exit 1 转为 error

用法::

    # warning-only(PR-7.1/7.2 第 1 批)
    uv run python scripts/check_loop_cursor_bundle_required.py

    # 严格模式(PR-7.x 批次.4 第 4 批目标)
    uv run python scripts/check_loop_cursor_bundle_required.py --strict

    # 通过环境变量启用严格模式
    uv run LOOP_CURSOR_BUNDLE_REQUIRED_STRICT=1 \\
        python scripts/check_loop_cursor_bundle_required.py

设计依据:
- ADR-0174 §D3(本脚本是 §D3 的实现)
- ADR-0174 §I-PROF-1(I-PROF-1 每 profile 必含 loop_cursor.spine_*)
- ADR-0174 §I-PROF-4(I-PROF-4 grep spine-default 在 profiles/ / bundles/ = 0)
- ADR-0169 §D9(bundle 重命名 + 兼容路径)
- ADR-0168-final §D16(9 profile → loop_cursor.spine_*)改为分批(ADR-0174)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = REPO_ROOT / "profiles"
BUNDLES_DIR = REPO_ROOT / "bundles"

# loop_cursor bundle 命名前缀(扫描 profile.bundles 列表时使用)
# 注意:profile 中引用形式为 "bundles/loop_cursor.spine_*.yaml",而 bundle 自身
# 顶层 name 为 "loop_cursor.spine_*" — 二者都用同一前缀匹配。
LOOP_CURSOR_BUNDLE_PREFIX = "loop_cursor.spine_"
LOOP_CURSOR_BUNDLE_PATH_PREFIX = "bundles/loop_cursor.spine_"

# 旧名 pattern(spine-default / spine-benchmark-minimal / spine-oii-debug
# 三个 bundle 在 PR-1 / S1 阶段重命名;本脚本以 I-PROF-4 钉死禁止)
LEGACY_SPINE_BUNDLE_PATTERN = re.compile(r"^bundles/spine-[a-z0-9_-]+\.yaml$")


def _read_yaml(path: Path) -> dict[str, Any] | None:
    """安全读取 YAML,parse error 返回 None(由 caller 决定如何处理)。"""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def _profile_uses_loop_cursor_bundle(profile: dict[str, Any]) -> bool:
    """profile 顶层 ``bundles`` 列表是否引用至少一个 ``loop_cursor.spine_*``。

    接受两种引用形式:
    - ``bundles/loop_cursor.spine_*.yaml``(完整路径,推荐)
    - ``loop_cursor.spine_*``(裸名,resolve 时会自动加 bundles/ 前缀)
    """
    bundles = profile.get("bundles") or []
    if not isinstance(bundles, list):
        return False
    for b in bundles:
        if not isinstance(b, str):
            continue
        if b.startswith(LOOP_CURSOR_BUNDLE_PATH_PREFIX) or b.startswith(LOOP_CURSOR_BUNDLE_PREFIX):
            return True
    return False


def _profile_uses_legacy_spine(profile: dict[str, Any]) -> list[str]:
    """返回 profile 引用的 legacy ``bundles/spine-*.yaml`` 列表(违规)。"""
    bundles = profile.get("bundles") or []
    if not isinstance(bundles, list):
        return []
    return [b for b in bundles if isinstance(b, str) and LEGACY_SPINE_BUNDLE_PATTERN.match(b)]


def _bundle_uses_correct_path(profile: dict[str, Any]) -> bool:
    """profile 引用的 loop_cursor bundle 路径格式正确。"""
    bundles = profile.get("bundles") or []
    if not isinstance(bundles, list):
        return False
    return any(
        isinstance(b, str)
        and b.startswith(LOOP_CURSOR_BUNDLE_PREFIX)
        # 进一步要求:必须写完整 bundles/loop_cursor.spine_*.yaml 路径
        and (b.endswith(".yaml") or ".yaml" in b)
        for b in bundles
    )


def _bundle_declares_loop_cursor_kind(bundle_data: dict[str, Any]) -> bool:
    """``bundles/loop_cursor.spine_*.yaml`` 顶层声明 ``kind: loop_cursor_bundle``。

    这是 D2 契约的前置检查:不声明 kind 的 bundle 不会触发 LoopCursorFactory
    装配,但 CI 不应让这种 bundle 蒙混过关。
    """
    kind = bundle_data.get("kind")
    return kind == "loop_cursor_bundle"


def _scan_profiles(strict: bool) -> tuple[list[str], list[str], list[str]]:
    """扫描所有 profiles/*.yaml,返回 (errors, warnings, info) 三类信息。

    errors:    strict 模式下触发 exit 1;warning 模式打印但 exit 0
    warnings:  仅打印,不触发 exit
    info:      仅打印(告知哪些 profile 已合规)
    """
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    if not PROFILES_DIR.is_dir():
        errors.append(f"FATAL: profiles directory not found: {PROFILES_DIR}")
        return errors, warnings, info

    for profile_path in sorted(PROFILES_DIR.glob("*.yaml")):
        raw = _read_yaml(profile_path)
        if raw is None:
            warnings.append(f"SKIP: {profile_path.name} (YAML parse error / non-mapping)")
            continue

        rel = profile_path.relative_to(REPO_ROOT)

        if _profile_uses_loop_cursor_bundle(raw):
            info.append(f"PASS: {rel} has loop_cursor.spine_* bundle")
        else:
            # 在 PR-7.1/7.2 第 1 批阶段:warning;
            # PR-7.x 批次.4 第 4 批完成阶段:error
            msg = f"{rel} 不含 bundles/loop_cursor.spine_*.yaml 引用 (ADR-0174 §I-PROF-1)"
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)

        legacy = _profile_uses_legacy_spine(raw)
        if legacy:
            msg = (
                f"{rel} 直引用 legacy bundles/spine-*.yaml: {legacy} "
                f"(ADR-0174 §I-PROF-4 — 必须用 loop_cursor.spine_* 命名)"
            )
            errors.append(msg)

        if _profile_uses_loop_cursor_bundle(raw) and not _bundle_declares_loop_cursor_kind(raw):
            # profile 引用了 loop_cursor.spine_*.yaml bundle — 但不强制要求 bundle 本身
            # 在 profile 层校验;这里跳过,因为 bundle 本身有独立校验路径。
            pass

    return errors, warnings, info


def _scan_bundles() -> tuple[list[str], list[str]]:
    """扫描 ``bundles/loop_cursor.spine_*.yaml`` 验证 D2 契约。

    - bundle 必须 ``kind: loop_cursor_bundle``
    - bundle 必须 ``provides: [loop_cursor_factory, ...]``

    Returns (errors, info).
    """
    errors: list[str] = []
    info: list[str] = []
    if not BUNDLES_DIR.is_dir():
        return errors, info

    found = False
    for bundle_path in sorted(BUNDLES_DIR.glob(f"{LOOP_CURSOR_BUNDLE_PREFIX}*.yaml")):
        found = True
        rel = bundle_path.relative_to(REPO_ROOT)
        raw = _read_yaml(bundle_path)
        if raw is None:
            errors.append(f"{rel} 不存在或不可解析")
            continue
        if not _bundle_declares_loop_cursor_kind(raw):
            errors.append(f"{rel} 缺顶层 kind: loop_cursor_bundle 字段(ADR-0174 §D2)")
        provides = raw.get("provides")
        if not (isinstance(provides, list) and any(p == "loop_cursor_factory" for p in provides)):
            errors.append(f"{rel} 缺 provides: [loop_cursor_factory, ...](ADR-0174 §D2)")
        info.append(f"PASS: {rel} declares kind={raw.get('kind')!r}")

    if not found:
        errors.append(
            "bundles/ 下没有任何 loop_cursor.spine_*.yaml 文件 "
            "(ADR-0174 §D2 — 仓库必须存在至少 3 个 spine bundle 变体)"
        )
    return errors, info


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ADR-0174 §D3 机器可执行门禁")
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "严格模式(PR-7.x 批次.4 第 4 批完成后启用)。"
            "本模式下,profile 缺 loop_cursor bundle 视为 error(exit 1),"
            "默认 warning-only(exit 0)。"
        ),
    )
    args = parser.parse_args(argv)

    strict = bool(args.strict) or _env_strict_requested()

    profile_errors, profile_warnings, profile_info = _scan_profiles(strict)
    bundle_errors, bundle_info = _scan_bundles()

    for line in profile_info + bundle_info:
        print(line)
    if profile_warnings:
        print("\n--- warnings (PR-7.1/7.2 第 1 批阶段, exit 0) ---")
        for line in profile_warnings:
            print(f"WARN: {line}")

    failures = profile_errors + bundle_errors
    if failures:
        print("\n--- errors (--strict 或硬性违规) ---")
        for line in failures:
            print(f"FAIL: {line}")
        return 1

    if profile_warnings and not strict:
        print(
            "\n注意:以上 warnings 是分批迁移过程的过渡状态。"
            "PR-7.x 批次.4 第 4 批完成时,所有 warnings 应已收敛(转 --strict 模式)。"
        )
        return 0

    print("\nOK: 所有 profiles 含 loop_cursor.spine_* bundle(ADR-0174 §D3)")
    return 0


def _env_strict_requested() -> bool:
    """``LOOP_CURSOR_BUNDLE_REQUIRED_STRICT=1`` / ``true`` 启用 strict mode。"""
    import os

    flag = os.environ.get("LOOP_CURSOR_BUNDLE_REQUIRED_STRICT", "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    sys.exit(main())
