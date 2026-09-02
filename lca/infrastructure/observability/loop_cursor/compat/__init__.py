"""Compat layer for the loop_cursor module — sunset window.

This subpackage is the single discoverable location for everything
that still exists only because PR-21~24 (the cycle that migrates
business code off ``coord.*`` and onto ``cursor.advance(...)`` /
``cursor.record_*(...)``) has not landed yet.

Re-exports kept alive here
---------------------------

- ``CoordinatorAdapter`` — adapter over ``StepCoordinator`` plus the
  new ``LoopCursor``; lets the un-migrated body / brain / agent code
  keep using ``coord.begin_step``, ``coord.record_*``,
  ``coord.emit_phase``, ``coord.emit`` while the migration sweeps
  through.  Delete when ``rg ``coord.begin_step|coord.record_thinking
  |coord.emit_phase`` lca/cognition lca/body lca/runtime lca/agent``
  is 0 (tracked in the COMPAT block at the top of
  ``coordinator_adapter.py``).

- ``bind_current_*`` / ``reset_current_*`` / ``install_*`` /
  ``reset_*`` ContextVar helpers — the historic pair of thin
  re-export pairs that exist only for backwards compatibility with
  pre-consolidation imports.  The single source of truth lives in
  :mod:`lca.infrastructure.observability.loop_cursor.model_visible_binding`
  and :mod:`...reasoner_prompt_binding`; the ``bind_*`` aliases in
  this subpackage forward to the canonical ``install_*`` / ``reset_*``
  names.

Sunset tracking
----------------

Each item below corresponds to one of the four ADR-mandated deletion
conditions. When a grep drops to zero, the file is deleted and this
manifest shrinks. See ``README.md`` adjacent.

"""

from __future__ import annotations

# Re-export the historic alias pairs so callers using
# ``from lca.infrastructure.observability.loop_cursor.compat import
# install_run_cursor`` resolve to the canonical implementation.
from lca.infrastructure.observability.loop_cursor.bind import (
    install_run_cursor,
    reset_run_cursor,
)
from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
    CoordinatorAdapter,
    bind_current_cursor,
    current_cursor,
    get_current_cursor,
    reset_current_cursor,
)
from lca.infrastructure.observability.loop_cursor.model_visible_binding import (
    bind_current_capture,
    install_model_visible_capture,
    reset_current_capture,
    reset_model_visible_capture,
)
from lca.infrastructure.observability.loop_cursor.reasoner_prompt_binding import (
    bind_current_reasoner_prompt,
    get_current_reasoner_prompt,
    install_reasoner_prompt,
    reset_current_reasoner_prompt,
    reset_reasoner_prompt,
)

__all__ = [
    "CoordinatorAdapter",
    "bind_current_capture",
    "bind_current_cursor",
    "bind_current_reasoner_prompt",
    "current_cursor",
    "get_current_cursor",
    "get_current_reasoner_prompt",
    "install_model_visible_capture",
    "install_reasoner_prompt",
    "install_run_cursor",
    "reset_current_capture",
    "reset_current_cursor",
    "reset_current_reasoner_prompt",
    "reset_model_visible_capture",
    "reset_reasoner_prompt",
    "reset_run_cursor",
]
