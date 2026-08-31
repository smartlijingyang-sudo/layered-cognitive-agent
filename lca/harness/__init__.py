"""Harness — session spine command carrier, agent handles, sessions, skills.

"command dispatcher" 新命名(ADR-0119 followup-2): 顶层 docstring 与 ``lca.harness.command.dispatcher``
子模块路径沿用至今。语义不是 ADR-0119 决定 4 之后的 ``kernel_serve``
LCA 后台进程,而是 session spine (0090 / 0092) 命令接收面。完整命名空间
历史映射看 ``docs/adr/0119-followup-gateway-name-map.md``。

cordis migration complete. Submodules (lca.harness.command.dispatcher,
lca.harness.session.inbox, lca.harness.agent.handle, lca.harness.skills)
import directly from their respective submodules.

Re-exports removed (deleted in cordis migration):
- ScopedPluginHost, current_scope (was lca.harness.kernel.scope)
- PluginContext, PluginHandle, PluginHost, PluginSpec, PluginState,
  ServiceRecord, reconcile (was lca.infrastructure.plugin.kernel)
- manifest_from_entry, manifest_from_spec (was lca.harness.kernel.compat)

Use cordis.Context directly instead.
"""
