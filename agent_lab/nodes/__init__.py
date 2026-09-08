"""agent_lab/nodes — the ant-worker node library.

Skeleton (post-fusion, 2026-09-08): each phase has its own subpackage.
Legacy subpackages (control/event/llm/mv/reflect_legacy/think/tool) are
kept for backwards compatibility and will be migrated in subsequent PRs.

  nodes/passthrough/    — stateless 1-in-1-out workers (7)
  nodes/perceive/       — perception (4)
  nodes/think/          — reasoning (5)
  nodes/act/            — action / tool dispatch (4)
  nodes/reflect/        — reflection (3)
  nodes/remember/       — durable fact write + history fold (5)
  nodes/stop/           — stop policy (1)
  nodes/model_visible/  — model-visible assembly (3)
  nodes/lineage/        — observability (5)

Importing this package registers every node via its ``@node(...)``
decorator.  The runner can then resolve any factory by name.
"""

# Re-exports for callers that want a single import surface.
# Import every node subpackage so its @node(...) decorators run.
# New skeleton (preferred):
from agent_lab.nodes import (
    act,  # noqa: F401
    lineage,  # noqa: F401
    model_visible,  # noqa: F401
    passthrough,  # noqa: F401
    perceive,  # noqa: F401
    reflect,  # noqa: F401
    remember,  # noqa: F401
    stop,  # noqa: F401
    think,  # noqa: F401
)
# Legacy subpackages (kept for back-compat; migrate in subsequent PRs):
from agent_lab.nodes import (
    control,  # noqa: F401
    event,  # noqa: F401
    llm,  # noqa: F401
    mv,  # noqa: F401
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
