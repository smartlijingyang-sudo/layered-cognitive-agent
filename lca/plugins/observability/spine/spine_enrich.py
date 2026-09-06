"""COMPAT re-export — canonical module is infrastructure spine_enrich (ADR-0194 P2-06).

# COMPAT(owner: ADR-0194 P2-06, from: plugins/observability/spine/spine_enrich,
#         to: infrastructure/observability/spine/spine_enrich,
#         delete_when: rg 'lca.plugins.observability.spine.spine_enrich' lca/ = 0,
#         forbidden_new_usage: import from plugins path in new code)
"""

from lca.infrastructure.observability.spine.spine_enrich import (
    EnrichResult,
    I17Violation,
    enrich_spine_payload,
    get_active_field_producers,
    get_active_spine_enricher,
    reset_active_field_producers,
    reset_active_spine_enricher,
    set_active_field_producers,
    set_active_spine_enricher,
)

__all__ = [
    "EnrichResult",
    "I17Violation",
    "enrich_spine_payload",
    "get_active_field_producers",
    "get_active_spine_enricher",
    "reset_active_field_producers",
    "reset_active_spine_enricher",
    "set_active_field_producers",
    "set_active_spine_enricher",
]
