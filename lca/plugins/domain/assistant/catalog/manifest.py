"""manifest 派生辅助：修订快照字段复制、list 摘要构造、字段取值。

这些 helper 只读 manifest / Home 磁盘，不产生事实；供 ``handlers`` 的
``get / list / revise_profile / reimport`` 复用。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import structlog

from lca.contracts.protocols.assistant.catalog import AssistantSummary
from lca.infrastructure.assistant.io import read_json
from lca.plugins.assistant.home._home_layout import (
    DEFAULT_TEMPLATE_ID,
    compute_digests,
    count_yaml_in,
    diff_digests,
)

log = structlog.get_logger(__name__)


def _copy_manifest_extras(source: Mapping[str, object], target: dict[str, object]) -> None:
    """把 manifest 中非 digest 派生字段（role_id / skills / tools 索引等）复制到修订版。"""
    for key in ("role_id", "skills", "tools"):
        if key in source:
            target[key] = source[key]


def _summary_from_home(home_dir: Path) -> AssistantSummary | None:
    """从一个 candidate home dir 构造 AssistantSummary;失败返回 None。"""
    manifest_path = home_dir / "manifest.json"
    if not manifest_path.is_file():
        log.warning("assistant.catalog.list.skip_no_manifest", home=str(home_dir))
        return None
    try:
        manifest = read_json(manifest_path)
    except (OSError, ValueError) as exc:
        log.warning(
            "assistant.catalog.list.skip_bad_manifest",
            home=str(home_dir),
            error=str(exc),
        )
        return None

    assistant_id = str(manifest.get("assistant_id") or home_dir.name)
    declared_digests_raw = manifest.get("digests") or {}
    if not isinstance(declared_digests_raw, dict):
        log.warning(
            "assistant.catalog.list.skip_bad_digests",
            assistant_id=assistant_id,
            home=str(home_dir),
        )
        return None
    declared_digests: dict[str, str] = {
        name: str(value) for name, value in declared_digests_raw.items() if isinstance(value, str)
    }
    actual_digests = compute_digests(home_dir)
    mismatches = diff_digests(declared_digests, actual_digests)
    if mismatches:
        log.warning(
            "assistant.catalog.list.skip_digest_mismatch",
            assistant_id=assistant_id,
            mismatches=mismatches,
        )
        return None

    profile_path = home_dir / "profile.json"
    profile = read_json(profile_path) if profile_path.is_file() else {}
    skills_dir = home_dir / "skills"
    return AssistantSummary(
        assistant_id=assistant_id,
        name=str(profile.get("name", assistant_id)),
        status=str(profile.get("status", "active")),
        template_id=_str_or_default(manifest.get("template_id"), DEFAULT_TEMPLATE_ID),
        revision_seq=_int_or_default(manifest.get("revision_seq"), 0),
        home_path=str(home_dir),
        skill_count=sum(1 for _ in skills_dir.iterdir()) if skills_dir.is_dir() else 0,
        job_count=count_yaml_in(home_dir / "routines"),
        updated_at=_str_or_default(manifest.get("created_at"), ""),
    )


def _str_or_default(value: object, default: str) -> str:
    """mypy 兼容的 manifest 字段取值;非字符串回退 default。"""
    return value if isinstance(value, str) else default


def _int_or_default(value: object, default: int) -> int:
    """mypy 兼容的 manifest 字段取值;非数字回退 default。"""
    if isinstance(value, bool):
        return default  # bool 是 int 子类,显式排除
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default
