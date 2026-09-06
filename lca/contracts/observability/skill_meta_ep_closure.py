"""Operational skill package meta-events — spine structural closure.

Global skill store mutations (``import_skill`` / ``activate_skill`` /
``search_skill``) emit both Session catalog facts (``.v1``) and spine
``skill.package.*`` EPs for grep-friendly cross-run debug.

Assistant Home skills continue to use ``assistant.skill.*`` (ADR-0187).
"""

from __future__ import annotations

from typing import Final

from lca.contracts.models.observability.event import (
    EventAudience,
    EventDescriptor,
    EventDurability,
    EventPlane,
    EventSensitivity,
)

SKILL_PACKAGE_INSTALLED: Final[str] = "skill.package.installed"
SKILL_PACKAGE_INSTALL_FAILED: Final[str] = "skill.package.install.failed"
SKILL_PACKAGE_ACTIVATED: Final[str] = "skill.package.activated"
SKILL_PACKAGE_SEARCHED: Final[str] = "skill.package.searched"

SKILL_META_EVENT_POINTS: Final[tuple[str, ...]] = (
    SKILL_PACKAGE_INSTALLED,
    SKILL_PACKAGE_INSTALL_FAILED,
    SKILL_PACKAGE_ACTIVATED,
    SKILL_PACKAGE_SEARCHED,
)

_EMITTER = "lca.infrastructure.tools.skills"


def all_skill_meta_event_descriptors() -> tuple[EventDescriptor, ...]:
    common = dict(
        plane=EventPlane.STRUCTURAL,
        domain="event",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.AUDITOR,
        sensitivity=EventSensitivity.INTERNAL,
        required=("skill_id",),
    )
    return (
        EventDescriptor(
            type_name=SKILL_PACKAGE_INSTALLED,
            emitter=_EMITTER,
            description="Global skill package installed to local store",
            **common,
        ),
        EventDescriptor(
            type_name=SKILL_PACKAGE_INSTALL_FAILED,
            emitter=_EMITTER,
            description="Global skill package install rejected",
            required=("reason",),
            plane=EventPlane.STRUCTURAL,
            domain="event",
            durability=EventDurability.REQUIRED,
            audience=EventAudience.AUDITOR,
            sensitivity=EventSensitivity.INTERNAL,
        ),
        EventDescriptor(
            type_name=SKILL_PACKAGE_ACTIVATED,
            emitter=_EMITTER,
            description="Global skill activated into agent context",
            **common,
        ),
        EventDescriptor(
            type_name=SKILL_PACKAGE_SEARCHED,
            emitter=_EMITTER,
            description="Skill market/local search executed",
            required=("query", "result_count"),
            plane=EventPlane.STRUCTURAL,
            domain="event",
            durability=EventDurability.REQUIRED,
            audience=EventAudience.AUDITOR,
            sensitivity=EventSensitivity.INTERNAL,
        ),
    )


__all__ = [
    "SKILL_META_EVENT_POINTS",
    "SKILL_PACKAGE_ACTIVATED",
    "SKILL_PACKAGE_INSTALL_FAILED",
    "SKILL_PACKAGE_INSTALLED",
    "SKILL_PACKAGE_SEARCHED",
    "all_skill_meta_event_descriptors",
]
