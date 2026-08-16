"""Mount every capability seam: Definition on ctx, then Providers, then catalog.

L4 是唯一知道全部具体类的组合根。Consumer 只拿 ctx.<key>（Definition）。
"""

from __future__ import annotations

from lca.contracts.mechanisms import SeamRole, register_seam, require_complete
from lca.contracts.mechanisms.capability import REQUIRED_SEAM_KEYS, SeamKey
from lca.contracts.protocols import LLMAdapter, MemorySystem, Sandbox, StateStore, Tool
from lca.contracts.protocols.infra import AgentTransport
from lca.contracts.protocols.journal import JournalProjector
from lca.contracts.protocols.observability import ObservabilityBackend
from lca.contracts.protocols.operational_skills import SkillPackageStore
from lca.layer0_infra.capability import (
    CapabilityHub,
    FileStoreService,
    LlmService,
    MemoryService,
    ObservabilityService,
    SandboxService,
    SearchService,
    SkillsService,
    StateStoreService,
    ToolsService,
    TransportService,
)
from lca.layer0_infra.file_store import FileStore, LocalFileStore, get_default_file_store
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer0_infra.observability.registry import create_observability
from lca.layer0_infra.sandbox.factory import resolve_sandbox
from lca.layer0_infra.sandbox.onlyboxes_adapter import OnlyboxesSandboxAdapter
from lca.layer0_infra.sandbox.runtime import RunBoundSandboxRuntime
from lca.layer0_infra.search.providers.tavily import search_tavily
from lca.layer0_infra.skills.disk_store import DiskSkillPackageStore
from lca.layer0_infra.skills.factory import resolve_skill_store
from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore
from lca.layer0_infra.tools.web_search import WebSearchExecutor
from lca.layer0_infra.transport.a2a_transport import A2ATransport
from lca.layer0_infra.transport.agent_transport import InternalTransport
from lca.layer0_infra.transport.mcp_transport import MCPTransport
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.brain.reasoner import PromptReasoner
from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer3_agent.cognitive_agent import CognitiveAgent


def new_capability_hub() -> CapabilityHub:
    """Empty ctx with every Definition mounted (no providers yet)."""
    ctx = CapabilityHub()
    ctx.mount(SeamKey.LLM.value, LlmService())
    ctx.mount(SeamKey.SANDBOX.value, SandboxService())
    ctx.mount(SeamKey.MEMORY.value, MemoryService())
    ctx.mount(SeamKey.STATE_STORE.value, StateStoreService())
    ctx.mount(SeamKey.SEARCH.value, SearchService())
    ctx.mount(SeamKey.TOOLS.value, ToolsService())
    ctx.mount(SeamKey.TRANSPORT.value, TransportService())
    ctx.mount(SeamKey.SKILLS.value, SkillsService())
    ctx.mount(SeamKey.FILE_STORE.value, FileStoreService())
    ctx.mount(SeamKey.OBSERVABILITY.value, ObservabilityService())
    return ctx


def mount_default_providers(ctx: CapabilityHub) -> CapabilityHub:
    """Hang built-in Providers onto Definition services."""
    llm: LlmService = ctx.require(SeamKey.LLM.value)
    llm.register("mock", MockLLMAdapter())

    sandbox: SandboxService = ctx.require(SeamKey.SANDBOX.value)
    resolved = resolve_sandbox()
    if resolved is not None:
        sandbox.register("active", resolved, activate=True)

    memory: MemoryService = ctx.require(SeamKey.MEMORY.value)
    memory.register("simple", SimpleMemorySystem)

    stores: StateStoreService = ctx.require(SeamKey.STATE_STORE.value)
    stores.register("memory", InMemoryStateStore)

    search: SearchService = ctx.require(SeamKey.SEARCH.value)
    search.register("tavily", search_tavily)

    transport: TransportService = ctx.require(SeamKey.TRANSPORT.value)
    for provider in (InternalTransport(), A2ATransport(), MCPTransport()):
        transport.register(provider)

    skills: SkillsService = ctx.require(SeamKey.SKILLS.value)
    skills.register("disk", resolve_skill_store())

    files: FileStoreService = ctx.require(SeamKey.FILE_STORE.value)
    files.register("local", get_default_file_store())

    obs: ObservabilityService = ctx.require(SeamKey.OBSERVABILITY.value)
    obs.register("console", lambda: create_observability("console"))
    return ctx


def register_seam_catalog() -> None:
    """三角色目录：Definition / Provider / Consumer。缺一不算 seam。"""
    register_seam(LlmService, SeamKey.LLM.value, SeamRole.DEFINITION)
    register_seam(MockLLMAdapter, SeamKey.LLM.value, SeamRole.PROVIDER)
    register_seam(PromptReasoner, SeamKey.LLM.value, SeamRole.CONSUMER)

    register_seam(SandboxService, SeamKey.SANDBOX.value, SeamRole.DEFINITION)
    register_seam(OnlyboxesSandboxAdapter, SeamKey.SANDBOX.value, SeamRole.PROVIDER)
    register_seam(RunBoundSandboxRuntime, SeamKey.SANDBOX.value, SeamRole.CONSUMER)

    register_seam(MemoryService, SeamKey.MEMORY.value, SeamRole.DEFINITION)
    register_seam(SimpleMemorySystem, SeamKey.MEMORY.value, SeamRole.PROVIDER)
    register_seam(CognitiveRuntime, SeamKey.MEMORY.value, SeamRole.CONSUMER)

    register_seam(StateStoreService, SeamKey.STATE_STORE.value, SeamRole.DEFINITION)
    register_seam(InMemoryStateStore, SeamKey.STATE_STORE.value, SeamRole.PROVIDER)
    register_seam(CognitiveRuntime, SeamKey.STATE_STORE.value, SeamRole.CONSUMER)

    register_seam(SearchService, SeamKey.SEARCH.value, SeamRole.DEFINITION)
    register_seam(search_tavily, SeamKey.SEARCH.value, SeamRole.PROVIDER)
    register_seam(WebSearchExecutor, SeamKey.SEARCH.value, SeamRole.CONSUMER)

    register_seam(ToolsService, SeamKey.TOOLS.value, SeamRole.DEFINITION)
    register_seam(Tool, SeamKey.TOOLS.value, SeamRole.PROVIDER)
    register_seam(SimpleSafeExecutor, SeamKey.TOOLS.value, SeamRole.CONSUMER)
    register_seam(PromptReasoner, SeamKey.TOOLS.value, SeamRole.CONSUMER)
    register_seam(SimpleBody, SeamKey.TOOLS.value, SeamRole.CONSUMER)

    register_seam(TransportService, SeamKey.TRANSPORT.value, SeamRole.DEFINITION)
    register_seam(InternalTransport, SeamKey.TRANSPORT.value, SeamRole.PROVIDER)
    register_seam(A2ATransport, SeamKey.TRANSPORT.value, SeamRole.PROVIDER)
    register_seam(MCPTransport, SeamKey.TRANSPORT.value, SeamRole.PROVIDER)
    register_seam(SimpleBody, SeamKey.TRANSPORT.value, SeamRole.CONSUMER)

    register_seam(SkillsService, SeamKey.SKILLS.value, SeamRole.DEFINITION)
    register_seam(DiskSkillPackageStore, SeamKey.SKILLS.value, SeamRole.PROVIDER)
    register_seam(CognitiveAgent, SeamKey.SKILLS.value, SeamRole.CONSUMER)

    register_seam(FileStoreService, SeamKey.FILE_STORE.value, SeamRole.DEFINITION)
    register_seam(LocalFileStore, SeamKey.FILE_STORE.value, SeamRole.PROVIDER)
    register_seam(RunBoundSandboxRuntime, SeamKey.FILE_STORE.value, SeamRole.CONSUMER)

    register_seam(ObservabilityService, SeamKey.OBSERVABILITY.value, SeamRole.DEFINITION)
    register_seam(create_observability, SeamKey.OBSERVABILITY.value, SeamRole.PROVIDER)
    register_seam(CognitiveAgent, SeamKey.OBSERVABILITY.value, SeamRole.CONSUMER)

    # type inventory — keeps unused-import honest for Protocol markers
    _ = (
        LLMAdapter,
        MemorySystem,
        Sandbox,
        StateStore,
        AgentTransport,
        JournalProjector,
        ObservabilityBackend,
        SkillPackageStore,
        FileStore,
    )
    require_complete(*(key.value for key in REQUIRED_SEAM_KEYS))


def boot_capabilities() -> CapabilityHub:
    """Definition + default Providers + catalog. Composer 的标准入口。"""
    register_seam_catalog()
    return mount_default_providers(new_capability_hub())
