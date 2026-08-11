"""Operational skill package infrastructure (ADR-0048 / ADR-0054)."""

from lca.layer0_infra.skills.activation_scope import (
    ActivatedSkill,
    activated_skills_scope,
    get_activated_skills,
    get_newly_activated,
    register_activated,
    resolve_skill_for_exec,
)
from lca.layer0_infra.skills.bundled import OFFICECLI_SKILL_ID, ensure_bundled_skills
from lca.layer0_infra.skills.disk_store import DiskSkillPackageStore
from lca.layer0_infra.skills.exec_bootstrap import (
    build_skill_exec_code,
    skill_mount_dir,
)
from lca.layer0_infra.skills.factory import resolve_skill_importer, resolve_skill_store
from lca.layer0_infra.skills.http_importer import HttpSkillImporter

__all__ = [
    "OFFICECLI_SKILL_ID",
    "ActivatedSkill",
    "DiskSkillPackageStore",
    "HttpSkillImporter",
    "activated_skills_scope",
    "build_skill_exec_code",
    "ensure_bundled_skills",
    "get_activated_skills",
    "get_newly_activated",
    "register_activated",
    "resolve_skill_for_exec",
    "resolve_skill_importer",
    "resolve_skill_store",
    "skill_mount_dir",
]
