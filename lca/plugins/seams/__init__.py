"""Tier-1 seam definitions (cordis @plugin modules), grouped by cognitive plane.

Each module in this package declares one capability seam: it provides a
factory registry (or the canonical class instance) that Tier-2 providers
register implementations into, and that Tier-3 plugins consume.

Subpackages (per ADR-0105 §11.x, Phase B #5):

* ``lca.plugins.seams.state`` — state-related registries
  (state_store, run_mode_registry, runtime_lifecycle_registry,
  component_registry).
* ``lca.plugins.seams.perceive`` — observation seam
  (observability_service, phase_observer_registry).
* ``lca.plugins.seams.think`` — reasoning seam
  (reasoner_template_catalog, system_prompt, llm, llm_resolver).
* ``lca.plugins.seams.gate`` — decision seam
  (gate_chain_composer, decision_classifier).
* ``lca.plugins.seams.act`` — execution seam
  (action_handler, delta_handler, effect_handler, tools, sandbox,
  transport).
* ``lca.plugins.seams.memory`` — durable memory seam
  (memory, skills, attachment, workspace, file_store, search,
  remember_effects).
* ``lca.plugins.seams.collaboration`` — multi-agent seam
  (team_seam, team_caster, team_casting_prompt_renderer, team_role_library,
  team_communication, team_shared_memory, session_service).
* ``lca.plugins.seams.journal`` — journaling seam
  (artifact_closure, composition_invariant, journal_store,
  journal_store_factories, idempotency_store).
* ``lca.plugins.seams.observability`` — observability-specific
  seam registries (attribute_policy, cli_debug, event_descriptor,
  evidence_store, fact_reader, fact_scorer, genai, journal, run_locator,
  run_ledger, tracer, trace_tool, w3c_validator, profile_snapshot,
  event_identity).

Conventions:

* Each seam declares an empty ``NamedRegistry`` (or its domain-specific
  service class) on the ``cordis.Context``; providers register
  implementations via ``ctx.require(...).register(...)``.
* Plugin ids follow ``lca-<name>-seam`` / ``lca-<name>-service`` so
  bundle YAML entries can opt in / out cleanly.
* LLM is the exception: ``llm_resolver`` is the sole owner of
  ``LLM_API_KEY`` and registers the chat adapter (see
  :mod:`lca.plugins.seams.think.llm_resolver`).
"""
