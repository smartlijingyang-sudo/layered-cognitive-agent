"""Barrel consistency — the ``sections/`` package must not silently drop a section.

Guards the ``sections.py`` → ``sections/`` package split: every section class
that used to live in the single module stays importable from the package
barrel, and the concrete classes still cover exactly the registered section
name set.
"""

from __future__ import annotations

import importlib

# The full section-class set that lived in the pre-split module.
_SECTION_CLASSES = (
    "ActivatedSkillsSection",
    "AssignedRolesSection",
    "AutonomousPresetsSection",
    "AvailableSkillsSection",
    "BackstorySection",
    "CloudSandboxSection",
    "ContextSection",
    "CurrentDateSection",
    "EvidencePackSection",
    "GoalSection",
    "HierarchicalInstructionsSection",
    "HomeSection",
    "MemberReportsSection",
    "MemberStatusSection",
    "ReactToolUsageSection",
    "ReactWorkflowSection",
    "RoleSection",
    "RoutingInstructionsSection",
    "StaticTextSection",
    "TaskSection",
    "TeammatesSection",
    "ToolsSection",
    "UserProfileSection",
    "VocalContractSection",
)

# ``StaticTextSection`` is the base class for the static text sections and
# has no fixed ``name``; every other class maps to one registered section name.
_CONCRETE_SECTION_NAMES = frozenset(
    {
        "activated_skills",
        "assigned_roles_text",
        "autonomous_presets",
        "available_skills",
        "backstory",
        "cloud_sandbox",
        "context",
        "current_date",
        "evidence_pack_text",
        "goal",
        "hierarchical_instructions",
        "home",
        "member_reports_text",
        "member_status_text",
        "react_tool_usage_guidelines",
        "react_workflow",
        "role",
        "routing_instructions",
        "task",
        "teammates",
        "tools",
        "user_profile",
        "vocal_contract",
    }
)


def _package() -> object:
    return importlib.import_module("lca.plugins.prompts.sections")


def test_barrel_exposes_every_section_class() -> None:
    package = _package()

    for name in _SECTION_CLASSES:
        assert hasattr(package, name), f"barrel dropped section class {name!r}"
        assert name in package.__all__, f"{name} missing from barrel __all__"


def test_barrel_reexports_registration_entrypoints() -> None:
    package = _package()

    setup_obj = getattr(package, "setup", None)
    assert setup_obj is not None, "barrel dropped setup"
    assert callable(getattr(setup_obj, "setup", None))
    assert "setup" in package.__all__
    assert package.Config is not None
    assert "Config" in package.__all__


def test_concrete_section_names_match_registered_closed_set() -> None:
    """The concrete section classes still cover exactly the registered names."""
    package = _package()

    concrete_names = {
        getattr(package, class_name).name
        for class_name in _SECTION_CLASSES
        if class_name != "StaticTextSection"
    }
    assert concrete_names == _CONCRETE_SECTION_NAMES
    assert len(concrete_names) == len(_SECTION_CLASSES) - 1
