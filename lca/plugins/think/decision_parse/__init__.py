"""think.decision_parse — typed-boundary adapter for LLMResponse → Decision.

The graph node registered as ``think::decision.parse`` wraps the pure
``decision_parse`` async fn in :mod:`lca.framework.graph.nodes.decision_parse`
with a ``NodeExecutor`` adapter so :class:`lca.harness.plugin_api.PluginContext`
can expose it under the composite key.

delete-when: never — this plugin is the typed-boundary adapter required by
``bundles/concept/decision_parse.yaml``'s ``factory: decision.parse``.
"""

from lca.plugins.think.decision_parse.execute import (
    DecisionParseExecutor,
    setup,
)

__all__ = ["DecisionParseExecutor", "setup"]
