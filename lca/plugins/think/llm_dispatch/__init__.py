"""think.llm_dispatch — typed-boundary adapter for LLM call + persist-before-execute.

The graph node registered as ``think::llm.call`` wraps the pure
``llm_dispatch`` async fn in :mod:`lca.framework.graph.nodes.llm_dispatch`
with a ``NodeExecutor`` adapter so :class:`lca.harness.plugin_api.PluginContext`
can expose it under the composite key.

delete-when: never — this plugin is the typed-boundary adapter required by
``bundles/concept/llm_dispatch.yaml``'s ``factory: llm.call``.
"""

from lca.plugins.think.llm_dispatch.execute import (
    LLMDispatchExecutor,
    setup,
)

__all__ = ["LLMDispatchExecutor", "setup"]
