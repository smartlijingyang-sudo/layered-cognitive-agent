# COMPAT(owner: ADR-0194, from: lca.harness.declarative.lifecycle.phase_fact_emitter,
# to: lca.loop.phase_fact_emitter,
# delete_when: rg "from lca\\.harness\\.declarative\\.lifecycle\\.phase_fact_emitter" 生产引用归零,
# forbidden_new_usage: 新代码优先 from lca.loop.phase_fact_emitter import emit_phase_catalog_facts)
"""COMPAT re-export — see ``lca.loop.phase_fact_emitter``."""

from lca.loop.phase_fact_emitter import emit_phase_catalog_facts

__all__ = ["emit_phase_catalog_facts"]
