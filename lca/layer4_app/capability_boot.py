"""Mount every capability seam: Definition on ctx, then Providers, then catalog.

L4 是唯一知道全部具体类的组合根。Consumer 只拿 ctx.<key>（Definition）。
"""

from __future__ import annotations

from lca.contracts.mechanisms.capability import SeamKey
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
from lca.layer0_infra.file_store import get_default_file_store
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer0_infra.observability.registry import create_observability
from lca.layer0_infra.sandbox.factory import resolve_sandbox
from lca.layer0_infra.search.providers.tavily import search_tavily
from lca.layer0_infra.skills.factory import resolve_skill_store
from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore
from lca.layer0_infra.transport.a2a_transport import A2ATransport
from lca.layer0_infra.transport.agent_transport import InternalTransport
from lca.layer0_infra.transport.mcp_transport import MCPTransport
from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem


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
    """三角色目录：Definition / Provider / Consumer。缺一不算 seam。

    .. deprecated::
        Loader._check_seam_completeness() 已替代此函数。
        Transition: plugin modules declare seam info in PluginManifest,
        and the Loader validates completeness during reconcile.
    """
    import warnings

    warnings.warn(
        "register_seam_catalog() is deprecated; "
        "Loader handles seam completeness",
        DeprecationWarning,
        stacklevel=2,
    )


def boot_capabilities() -> CapabilityHub:
    """Definition + default Providers + catalog. Composer 的标准入口。

    .. note::
        Legacy path. New code should use profile-driven plugin loading
        via ``Loader.load()`` with ``AgentComposer.compose(scope=...)``.
    """
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        register_seam_catalog()
    return mount_default_providers(new_capability_hub())
