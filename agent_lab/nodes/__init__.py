"""agent_lab/nodes — the ant-worker node library.

Skeleton (post-fusion, 2026-09-08): each phase has its own subpackage.
Legacy subpackages (control/event/llm/model_visible/think/tool) are
kept for backwards compatibility and will be migrated in subsequent PRs.

  nodes/passthrough/    — stateless 1-in-1-out workers (7)
  nodes/perceive/       — perception (sensors → ContextManifest)
  nodes/model_eye/      — model eye (fold facts → frozen ContextManifest)
  nodes/think/          — reasoning (expose → reason → classify → guard)
  nodes/act/            — act phase (shape → authorize → execute → observe)
  nodes/reflect/        — reflection (join → critique → extract)
  nodes/remember/       — admit → commit → snapshot (+ fold_history)
  nodes/control/        — control slots (incl. stop_decide after remember)
  nodes/lineage/        — observability (5)

Importing this package registers every node via its ``@node(...)``
decorator.  The runner can then resolve any factory by name.
"""

# Import every node subpackage so its @node(...) decorators run.
from agent_lab.nodes import (
    act,  # noqa: F401
    control,  # noqa: F401
    event,  # noqa: F401
    lineage,  # noqa: F401
    llm,  # noqa: F401
    model_eye,  # noqa: F401
    model_visible,  # noqa: F401
    passthrough,  # noqa: F401
    perceive,  # noqa: F401
    reflect,  # noqa: F401
    remember,  # noqa: F401
    session_log,  # noqa: F401
    think,  # noqa: F401
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
