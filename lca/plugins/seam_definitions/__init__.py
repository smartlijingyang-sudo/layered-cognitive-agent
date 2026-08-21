"""Tier-1 seam definitions (cordis @plugin modules).

Each module in this package declares one capability seam: it provides a
factory registry (or the canonical class instance) that Tier-2 providers
register implementations into, and that Tier-3 plugins consume.

Sub-namespaces:

* ``lca.plugins.seam_definitions`` — base capability seams (llm, tools,
  transport, memory, sandbox, file_store, observability, skills,
  state_store, search, attachment, workspace, system_prompt,
  session_service, journal_store, journal_store_factories, llm_resolver).
* ``lca.plugins.seam_definitions.observability`` — observability-specific
  seam registries (attribute_policy, cli_debug, event_descriptor,
  evidence_store, fact_reader, fact_scorer, genai, journal, run_locator,
  tracer, trace_tool, w3c_validator).

Conventions:

* Each seam declares an empty ``NamedRegistry`` (or its domain-specific
  service class) on the ``cordis.Context``; providers register
  implementations via ``ctx.inject(...).register(...)``.
* Plugin ids follow ``lca-<name>-seam`` / ``lca-<name>-service`` so
  bundle YAML entries can opt in / out cleanly.
* LLM is the exception: ``llm_resolver`` is the sole owner of
  ``LLM_API_KEY`` and registers the chat adapter (see
  :mod:`lca.plugins.seam_definitions.llm_resolver`).
"""
