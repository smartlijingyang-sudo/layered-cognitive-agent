"""First-party operational skills shipped under repo ``skills/`` (ADR-0054).

Content packs live next to ``roles/`` (not inside the ``lca`` package tree).
``ensure_bundled_skills`` materializes them into ``DiskSkillPackageStore`` so
``activate_skill`` / AVAILABLE_SKILLS work offline without Market import.
"""

from __future__ import annotations

import logging
from pathlib import Path

from lca.contracts.protocols.operational_skills import SkillNotFoundError
from lca.layer0_infra.skills.disk_store import (
    DiskSkillPackageStore,
    content_hash,
    sanitize_skill_id,
)
from lca.layer0_infra.skills.frontmatter import split_frontmatter

logger = logging.getLogger(__name__)

# skill_id for the Office plane (format_routing + prompts).
OFFICECLI_SKILL_ID: str = "officecli"

_SKILL_MD = "SKILL.md"
_RESOURCES = "resources"
_BUNDLED_SOURCE_PREFIX = "bundled:"


def default_bundled_skills_root() -> Path:
    """Repo-root ``skills/`` directory (…/layered-cognitive-agent/skills)."""
    # lca/layer0_infra/skills/bundled.py → parents[3] = repo root
    return Path(__file__).resolve().parents[3] / "skills"


def ensure_bundled_skills(
    store: DiskSkillPackageStore,
    *,
    root: Path | None = None,
) -> tuple[str, ...]:
    """Install or refresh first-party skills; return skill_ids that were written.

    Idempotent: skips when installed ``content_hash`` matches source SKILL.md.
    Unknown directories without SKILL.md are ignored.
    """
    base = root if root is not None else default_bundled_skills_root()
    if not base.is_dir():
        return ()

    installed: list[str] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        skill_md = child / _SKILL_MD
        if not skill_md.is_file():
            continue
        try:
            skill_id = sanitize_skill_id(child.name)
        except ValueError:
            logger.warning("bundled skill dir has illegal name: %s", child.name)
            continue
        text = skill_md.read_text(encoding="utf-8")
        digest = content_hash(text.encode("utf-8"))
        if _already_current(store, skill_id, digest):
            continue
        resources = _load_resources(child / _RESOURCES)
        version = _version_from_skill_md(text)
        store.install_package(
            skill_id=skill_id,
            skill_md_text=text,
            resource_files=resources,
            source_url=f"{_BUNDLED_SOURCE_PREFIX}{skill_id}",
            version=version,
        )
        installed.append(skill_id)
        logger.info("bundled skill installed/updated: %s (version=%s)", skill_id, version or "-")
    return tuple(installed)


def _already_current(store: DiskSkillPackageStore, skill_id: str, digest: str) -> bool:
    try:
        package = store.get(skill_id)
    except SkillNotFoundError:
        return False
    return package.content_hash == digest


def _load_resources(resources_dir: Path) -> dict[str, bytes]:
    if not resources_dir.is_dir():
        return {}
    out: dict[str, bytes] = {}
    for path in sorted(resources_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(resources_dir).as_posix()
        out[rel] = path.read_bytes()
    return out


def _version_from_skill_md(text: str) -> str:
    meta, _ = split_frontmatter(text)
    raw = meta.get("version")
    return str(raw).strip() if raw is not None else ""
