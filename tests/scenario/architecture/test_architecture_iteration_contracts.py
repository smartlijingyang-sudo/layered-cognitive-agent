"""架构深化回归：每条记录固定一个模块的公开测试表面。"""

import importlib

import pytest

CASES: list[tuple[str, str]] = [
    ("lca.contracts.models.core.state.state", "AgentState"),
    ("lca.contracts.models.core.policy.budget", "BudgetLimits"),
    ("lca.contracts.models.core.execution.decision", "Decision"),
    ("lca.contracts.models.core.execution.execution", "ExecutionEnvelope"),
    ("lca.contracts.models.core.state.lifecycle", "TaskStatus"),
    ("lca.contracts.models.core.conversation.llm", "LLMResponse"),
    ("lca.contracts.models.core.conversation.message", "AgentMessage"),
    ("lca.contracts.models.core.perceive.perception", "ContextManifest"),
    ("lca.contracts.models.core.state.plane", "PlaneBindings"),
    ("lca.contracts.models.core.execution.result", "Result"),
    ("lca.contracts.models.core.execution.sandbox", "SessionInfo"),
    ("lca.contracts.models.core.workspace.activation", "ActivatedSkill"),
    ("lca.contracts.models.core.workspace.approval", "ApprovalRequest"),
    ("lca.contracts.models.core.conversation.attachment", "AttachmentRecord"),
    ("lca.contracts.models.core.conversation.conversation", "ConversationTurn"),
    ("lca.contracts.models.core.conversation.memory", "MemoryRecord"),
    ("lca.contracts.models.core.workspace.preinstall", "python_import_name"),
    ("lca.contracts.models.core.policy.gate_policy", "PolicyFact"),
    ("lca.contracts.models.core.state.guest_layout", "GuestLayout"),
    ("lca.contracts.harness.collaboration.subagent", "SubagentSpec"),
    ("lca.contracts.harness.tasks.task", "TaskStep"),
    ("lca.contracts.harness.gate.timeout_recovery", "TimeoutRecoveryPolicy"),
    ("lca.contracts.harness.act.tool_governance", "ToolGovernance"),
    ("lca.contracts.harness.act.trace_context", "AgentTraceContext"),
    ("lca.contracts.harness.tasks.workflow", "WorkflowProgress"),
    ("lca.contracts.mechanisms", "EventBus"),
    ("lca.contracts.mechanisms.capability.capability", "CapabilityKey"),
    ("lca.contracts.mechanisms.composition.composition", "PluginFactory"),
    ("lca.contracts.mechanisms.content.addressable", "ContentAddressableStore"),
    ("lca.contracts.mechanisms.factory.registry", "FactoryRegistry"),
    ("lca.contracts.mechanisms.plugin.plugin", "PluginConfig"),
    ("lca.contracts.mechanisms.registries.registries", "Registries"),
    ("lca.contracts.mechanisms.seam.seam", "consume"),
    ("lca.contracts.harness.memory.skill", "LoadedSkill"),
    ("lca.contracts.protocols.memory.operational_skills", "SkillPackage"),
    ("lca.harness.skills.projection", "SkillsProjection"),
    ("lca.harness.skills.service", "SkillCatalogService"),
    ("lca.infrastructure.capability.skills.skills", "SkillsService"),
    ("lca.infrastructure.search.skill.policy", "filter_skill_search_result"),
    ("lca.infrastructure.skills.activation.scope", "get_activated_skills"),
    ("lca.infrastructure.skills.bundled.bundled", "ensure_bundled_skills"),
    ("lca.infrastructure.skills.disk.store", "DiskSkillPackageStore"),
    ("lca.infrastructure.skills.factory.factory", "resolve_skill_store"),
    ("lca.infrastructure.skills.format.routing", "skills_for_filename"),
    ("lca.infrastructure.skills.frontmatter.frontmatter", "split_frontmatter"),
    ("lca.infrastructure.skills.http.importer", "HttpSkillImporter"),
    ("lca.infrastructure.skills.market.auth", "market_auth_setup_hint"),
    ("lca.infrastructure.skills.marketplace.marketplace", "LobeHubMarketClient"),
    ("lca.infrastructure.skills.settings.settings", "SkillSettings"),
    ("lca.infrastructure.skills.url.sources", "ParsedSkillUrl"),
    ("lca.infrastructure.skills.zip.security", "find_skill_markdown"),
    ("lca.contracts.protocols.memory.operational_skills", "SkillPackageInstaller"),
]


@pytest.mark.parametrize(("module_name", "symbol_name"), CASES)
def test_architecture_contract_is_explicit(module_name: str, symbol_name: str) -> None:
    module = importlib.import_module(module_name)
    assert hasattr(module, symbol_name), f"{module_name} must expose {symbol_name}"
    symbol = getattr(module, symbol_name)
    assert getattr(symbol, "__module__", module_name) == module_name
