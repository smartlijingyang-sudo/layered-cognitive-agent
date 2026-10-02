"""Prompt sections package — typed section classes + registration plugin.

The brain prompt is composed entirely from typed section providers. Each
section is a small class implementing ``PureSection`` or ``StatefulSection``;
the assembler walks a ``PromptTemplate``'s ``SectionReference`` list and
resolves each section through the ``PromptSectionRegistry``.

The Cordis plugin registration lives in
:mod:`lca.plugins.prompts.sections.plugin` (referenced by bundles as
``$module: lca.plugins.prompts.sections.plugin``); this package barrel
re-exports every section class so
``from lca.plugins.prompts.sections import ...`` keeps working.
"""

from __future__ import annotations

from lca.plugins.prompts.sections.base import (
    StaticTextSection,
    build_static_text,
)
from lca.plugins.prompts.sections.connected_services import (
    ConnectedServicesSection,
    build_connected_services,
    render_connected_services_text,
)
from lca.plugins.prompts.sections.context import (
    AutonomousPresetsSection,
    ContextSection,
    HomeSection,
    UserProfileSection,
    build_autonomous_presets,
    build_context,
    build_home,
    build_user_profile,
)
from lca.plugins.prompts.sections.evidence import (
    EvidencePackSection,
    build_evidence_pack,
)
from lca.plugins.prompts.sections.member_status import (
    MemberStatusSection,
    build_member_status,
)
from lca.plugins.prompts.sections.memory import (
    MemoryRetrievalSection,
    PrivacyFirewallSection,
    build_memory_retrieval,
    build_privacy_firewall,
)
from lca.plugins.prompts.sections.plugin import Config, setup
from lca.plugins.prompts.sections.role import (
    BackstorySection,
    GoalSection,
    RoleSection,
    build_backstory_section,
    build_goal_section,
    build_role_section,
)
from lca.plugins.prompts.sections.runtime_env import (
    DeveloperTimestampSection,
    RuntimeEnvSection,
    build_developer_timestamp,
    build_runtime_env,
    render_developer_timestamp,
    render_runtime_row,
)
from lca.plugins.prompts.sections.skills import (
    ActivatedSkillsSection,
    build_activated_skills,
)
from lca.plugins.prompts.sections.task import TaskSection, build_task
from lca.plugins.prompts.sections.teammates import (
    AssignedRolesSection,
    MemberReportsSection,
    TeammatesSection,
    build_assigned_roles,
    build_member_reports,
    build_teammates,
)
from lca.plugins.prompts.sections.text import (
    _REACT_TOOL_USAGE_TEXT as _REACT_TOOL_USAGE_TEXT,
)
from lca.plugins.prompts.sections.text import (
    HierarchicalInstructionsSection,
    ReactToolUsageSection,
    ReactWorkflowSection,
    RoutingInstructionsSection,
    build_hierarchical_instructions,
    build_react_tool_usage,
    build_react_workflow,
    build_routing_instructions,
)
from lca.plugins.prompts.sections.time import (
    CurrentDateSection,
    build_current_date,
)
from lca.plugins.prompts.sections.tools import (
    AvailableSkillsSection,
    CloudSandboxSection,
    ToolsSection,
    build_available_skills_section,
    build_cloud_sandbox_section,
    build_tools_section,
)
from lca.plugins.prompts.sections.vocal import (
    VocalContractSection,
    build_vocal_contract,
)

__all__ = [
    "ActivatedSkillsSection",
    "AssignedRolesSection",
    "AutonomousPresetsSection",
    "AvailableSkillsSection",
    "BackstorySection",
    "CloudSandboxSection",
    "Config",
    "ConnectedServicesSection",
    "ContextSection",
    "CurrentDateSection",
    "DeveloperTimestampSection",
    "EvidencePackSection",
    "GoalSection",
    "HierarchicalInstructionsSection",
    "HomeSection",
    "MemberReportsSection",
    "MemberStatusSection",
    "MemoryRetrievalSection",
    "PrivacyFirewallSection",
    "ReactToolUsageSection",
    "ReactWorkflowSection",
    "RoleSection",
    "RoutingInstructionsSection",
    "RuntimeEnvSection",
    "StaticTextSection",
    "TaskSection",
    "TeammatesSection",
    "ToolsSection",
    "UserProfileSection",
    "VocalContractSection",
    "build_activated_skills",
    "build_assigned_roles",
    "build_autonomous_presets",
    "build_available_skills_section",
    "build_backstory_section",
    "build_cloud_sandbox_section",
    "build_connected_services",
    "build_context",
    "build_current_date",
    "build_developer_timestamp",
    "build_evidence_pack",
    "build_goal_section",
    "build_hierarchical_instructions",
    "build_home",
    "build_member_reports",
    "build_member_status",
    "build_memory_retrieval",
    "build_privacy_firewall",
    "build_react_tool_usage",
    "build_react_workflow",
    "build_role_section",
    "build_routing_instructions",
    "build_runtime_env",
    "build_static_text",
    "build_task",
    "build_teammates",
    "build_tools_section",
    "build_user_profile",
    "build_vocal_contract",
    "render_connected_services_text",
    "render_developer_timestamp",
    "render_runtime_row",
    "setup",
]
