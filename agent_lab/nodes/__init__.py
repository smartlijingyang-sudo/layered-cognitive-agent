"""agent_lab/nodes — the ant-worker node library.

Each ``@node(...)`` class lives in its own file under one of:

  nodes/control/        — routing primitives (join, barrier, route_on, discard)
  nodes/llm/            — LLM call + message assembly + manifest commit
  nodes/tool/           — tool intent + grant + dispatch + receipt + integrate
  nodes/mv/             — model-visible assembly workers
  nodes/passthrough/    — identity / constant / select / redact / dedup / rank

Importing this package registers every node via its ``@node(...)``
decorator.  The runner can then resolve any factory by name.
"""

# Re-exports for callers that want a single import surface.
# Import every node subpackage so its @node(...) decorators run.
from agent_lab.nodes import (
    control,  # noqa: F401
    llm,  # noqa: F401
    mv,  # noqa: F401
    passthrough,  # noqa: F401
    tool,  # noqa: F401
)
from agent_lab.nodes.base import Node, NodeRegistry, invoke, register  # noqa: F401
from agent_lab.nodes.manifest import (  # noqa: F401
    NodeKind,
    NodeLayer,
    NodeManifest,
    PortInfo,
    PortKind,
    node,
)
