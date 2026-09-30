"""Context files as their own capability (ADR-0254).

A person can read the assistant's long-term context from files. The model
sees a bounded view of those files. Saying a fact was remembered is allowed
only after the file write succeeds.

Names, directories, and budgets live in ``layout.toml``. ``domain`` holds
the rules and depends only on the standard library.
``ports`` are the replaceable seams (file access, event delivery, and later
watch, compaction, retrieval, and dreaming). ``adapters`` are one strategy
each. ``service`` runs a use case. LCA maps its records in at the edge and
does not leak into this package, so another agent can reuse the package
without the LCA graph.
"""

from __future__ import annotations

__all__: list[str] = []
