"""Operational skill package meta-events — spine structural closure.

Global skill store mutations (``import_skill`` / ``activate_skill`` /
``search_skill``) emit both Session catalog facts (``.v1``) and spine
``skill.package.*`` EPs for grep-friendly cross-run debug.

Assistant Home skills continue to use ``assistant.skill.*`` (ADR-0187).
"""

from __future__ import annotations

from typing import Final

from lca.contracts.models.observability.event.event import (
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


def _skill_meta_descriptor(
    type_name: str,
    description: str,
    *,
    required: tuple[str, ...],
) -> EventDescriptor:
    return EventDescriptor(
        type_name=type_name,
        emitter=_EMITTER,
        description=description,
        plane=EventPlane.STRUCTURAL,
        domain="event",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.AUDITOR,
        sensitivity=EventSensitivity.INTERNAL,
        required=required,
    )


def all_skill_meta_event_descriptors() -> tuple[EventDescriptor, ...]:
    return (
        _skill_meta_descriptor(
            SKILL_PACKAGE_INSTALLED,
            "Global skill package installed to local store",
            required=("skill_id",),
        ),
        _skill_meta_descriptor(
            SKILL_PACKAGE_INSTALL_FAILED,
            "Global skill package install rejected",
            required=("reason",),
        ),
        _skill_meta_descriptor(
            SKILL_PACKAGE_ACTIVATED,
            "Global skill activated into agent context",
            required=("skill_id",),
        ),
        _skill_meta_descriptor(
            SKILL_PACKAGE_SEARCHED,
            "Skill market/local search executed",
            required=("query", "result_count"),
        ),
    )


__all__ = [
    "SKILL_META_EVENT_POINTS",
    "SKILL_PACKAGE_ACTIVATED",
    "SKILL_PACKAGE_INSTALLED",
    "SKILL_PACKAGE_INSTALL_FAILED",
    "SKILL_PACKAGE_SEARCHED",
    "all_skill_meta_event_descriptors",
]
