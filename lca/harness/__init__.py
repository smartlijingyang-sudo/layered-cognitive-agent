"""Harness — command gateway, agent handles, sessions, skills, etc.

cordis migration complete. Submodules (lca.harness.command.gateway,
lca.harness.session.inbox, lca.harness.agent.handle, lca.harness.skills)
import directly from their respective submodules.

Re-exports removed (deleted in cordis migration):
- ScopedPluginHost, current_scope (was lca.harness.kernel.scope)
- PluginContext, PluginHandle, PluginHost, PluginSpec, PluginState,
  ServiceRecord, reconcile (was lca.layer0_infra.plugin.kernel)
- manifest_from_entry, manifest_from_spec (was lca.harness.kernel.compat)

Use cordis.Context directly instead.
"""
