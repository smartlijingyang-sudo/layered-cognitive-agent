"""架构深化回归：每条记录固定一个模块的公开测试表面。"""

import importlib

import pytest

CASES: list[tuple[str, str]] = [
    ("lca.contracts.models.core.state", "AgentState"),
    ("lca.contracts.models.core.budget", "BudgetLimits"),
    ("lca.contracts.models.core.decision", "Decision"),
    ("lca.contracts.models.core.execution", "ExecutionEnvelope"),
    ("lca.contracts.models.core.lifecycle", "TaskStatus"),
    ("lca.contracts.models.core.llm", "LLMResponse"),
    ("lca.contracts.models.core.message", "AgentMessage"),
    ("lca.contracts.models.core.perception", "ContextManifest"),
    ("lca.contracts.models.core.plane", "PlaneBindings"),
    ("lca.contracts.models.core.result", "Result"),
    ("lca.contracts.models.core.sandbox", "SessionInfo"),
    ("lca.contracts.models.core.activation", "ActivatedSkill"),
    ("lca.contracts.models.core.approval", "ApprovalRequest"),
    ("lca.contracts.models.core.attachment", "AttachmentRecord"),
    ("lca.contracts.models.core.conversation", "ConversationTurn"),
    ("lca.contracts.models.core.memory", "MemoryRecord"),
    ("lca.contracts.models.core.preinstall", "python_import_name"),
    ("lca.contracts.models.core.gate_policy", "PolicyFact"),
    ("lca.contracts.models.core.guest_layout", "GuestLayout"),
    ("lca.contracts.harness.subagent", "SubagentSpec"),
    ("lca.contracts.harness.task", "TaskStep"),
    ("lca.contracts.harness.timeout_recovery", "TimeoutRecoveryPolicy"),
    ("lca.contracts.harness.tool_governance", "ToolGovernance"),
    ("lca.contracts.harness.trace_context", "AgentTraceContext"),
    ("lca.contracts.harness.workflow", "WorkflowProgress"),
    ("lca.contracts.mechanisms", "EventBus"),
    ("lca.contracts.mechanisms.capability", "CapabilityKey"),
    ("lca.contracts.mechanisms.composition", "PluginFactory"),
    ("lca.contracts.mechanisms.content_addressable", "ContentAddressableStore"),
    ("lca.contracts.mechanisms.factory_registry", "FactoryRegistry"),
    ("lca.contracts.mechanisms.plugin", "PluginConfig"),
    ("lca.contracts.mechanisms.registries", "Registries"),
    ("lca.contracts.mechanisms.seam", "consume"),
    ("lca.contracts.harness.skill", "LoadedSkill"),
    ("lca.contracts.protocols.operational_skills", "SkillPackage"),
    ("lca.harness.skills.projection", "SkillsProjection"),
    ("lca.harness.skills.service", "SkillCatalogService"),
    ("lca.layer0_infra.capability.skills", "SkillsService"),
    ("lca.layer0_infra.search.skill_policy", "filter_skill_search_result"),
    ("lca.layer0_infra.skills.activation_scope", "get_activated_skills"),
    ("lca.layer0_infra.skills.bundled", "ensure_bundled_skills"),
    ("lca.layer0_infra.skills.disk_store", "DiskSkillPackageStore"),
    ("lca.layer0_infra.skills.factory", "resolve_skill_store"),
    ("lca.layer0_infra.skills.format_routing", "skills_for_filename"),
    ("lca.layer0_infra.skills.frontmatter", "split_frontmatter"),
    ("lca.layer0_infra.skills.http_importer", "HttpSkillImporter"),
    ("lca.layer0_infra.skills.market_auth", "market_auth_setup_hint"),
    ("lca.layer0_infra.skills.marketplace", "LobeHubMarketClient"),
    ("lca.layer0_infra.skills.settings", "SkillSettings"),
    ("lca.layer0_infra.skills.url_sources", "ParsedSkillUrl"),
    ("lca.layer0_infra.skills.zip_security", "find_skill_markdown"),
    ("lca.contracts.protocols.operational_skills", "SkillPackageInstaller"),
]


@pytest.mark.parametrize(("module_name", "symbol_name"), CASES)
def test_architecture_contract_is_explicit(module_name: str, symbol_name: str) -> None:
    module = importlib.import_module(module_name)
    assert hasattr(module, symbol_name), f"{module_name} must expose {symbol_name}"
    symbol = getattr(module, symbol_name)
    assert getattr(symbol, "__module__", module_name) == module_name
