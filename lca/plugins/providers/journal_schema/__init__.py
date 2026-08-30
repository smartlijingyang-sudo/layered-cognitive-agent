"""Journal schema providers —— ADR-0096 MVA-1.

Plain classes registered into the ``journal_schemas`` registry at boot.
No ``@plugin`` decorator: the seam owns capability provision.
"""

from lca.plugins.providers.journal_schema.v2 import EnvelopeV2Schema

__all__ = ["EnvelopeV2Schema"]
