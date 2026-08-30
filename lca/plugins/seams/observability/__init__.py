"""Observability seam registries.

Each module in this package declares an empty ``NamedRegistry`` (or its
canonical instance) on the ``cordis.Context``. Tier-2 provider plugins
under ``lca.plugins.providers`` register concrete implementations into
these registries at boot time.

Seams:

* ``attribute_policy_backends`` — attribute allow/deny policies.
* ``cli_debug_command`` — ``lca-ops debug`` handlers.
* ``event_descriptor_registry`` — 49+ ``EventDescriptor`` definitions.
* ``evidence_store`` / ``evidence_policy`` — filesystem-backed evidence.
* ``fact_readers`` — ``JournalProjector`` factories for telemetry.
* ``fact_scorers`` — scoring functions over facts.
* ``genai_semantic_mapper`` — LLM/Tool/Code/Permission/Retry mappers.
* ``journal_backends`` — journal stores (memory / fs / OTel).
* ``run_locator`` — run id → filesystem locator.
* ``tracer_backends`` — OTel tracer factories.
* ``trace_inspector_tools`` — trace inspection tools.
* ``w3c_trace_context_validator`` — W3C trace context validator.
"""
