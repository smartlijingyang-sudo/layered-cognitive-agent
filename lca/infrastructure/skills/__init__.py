"""Operational skill package infrastructure (ADR-0048 / ADR-0054)."""

from lca.infrastructure.skills.activation.scope import (
    MAX_ACTIVATED_SKILLS_PER_RUN,
    ActivatedSkill,
    activated_skills_scope,
    can_activate,
    get_activated_skills,
    get_newly_activated,
    register_activated,
    resolve_skill_for_exec,
    unregister_activated,
)
from lca.infrastructure.skills.bundled.bundled import OFFICECLI_SKILL_ID, ensure_bundled_skills
from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
from lca.infrastructure.skills.exec.bootstrap import (
    build_skill_exec_code,
    skill_mount_dir,
)
from lca.infrastructure.skills.factory.factory import resolve_skill_importer, resolve_skill_store
from lca.infrastructure.skills.http.importer import HttpSkillImporter

__all__ = [
    "MAX_ACTIVATED_SKILLS_PER_RUN",
    "OFFICECLI_SKILL_ID",
    "ActivatedSkill",
    "DiskSkillPackageStore",
    "HttpSkillImporter",
    "activated_skills_scope",
    "build_skill_exec_code",
    "can_activate",
    "ensure_bundled_skills",
    "get_activated_skills",
    "get_newly_activated",
    "register_activated",
    "resolve_skill_for_exec",
    "resolve_skill_importer",
    "resolve_skill_store",
    "skill_mount_dir",
    "unregister_activated",
]
