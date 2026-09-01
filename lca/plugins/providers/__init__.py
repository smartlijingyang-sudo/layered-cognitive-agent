"""Tier-2 Provider plugins, partitioned into 14 subpackages.

Each Tier-1 seam in ``lca.plugins.seams`` has one or more provider
plugins here that register implementations. LLM is the exception: its
credentials and chat adapter are owned solely by
``lca.plugins.seams.think.llm_resolver``.

Subpackages (per ADR-0105 §11.x, Phase B #6):

Seam-mirror subpackages (each provider joins its seam's group):

* ``state`` — ``state_store``, ``component_state_store``,
  ``runtime_lifecycle``, ``runtime_lifecycle_logging``,
  ``component_budget_policy``.
* ``perceive`` — ``phase_observer``, ``phase_observer_tracing``.
* ``think`` — ``cognitive_think_pipeline``,
  ``cognitive_reflection_pipeline``, ``composition_composer``,
  ``composition_provider``, ``loop_guard``, ``llm`` (retired stub).
* ``gate`` — ``gate_chain_composer``, ``decision_classifier``.
* ``act`` — ``action_handlers``, ``delta_handlers``,
  ``delta_handler_registry``, ``effect_handlers``, ``sandbox``,
  ``transport``, ``tools``, ``tool_batch_execution_policy``.
* ``memory`` — ``attachment``, ``component_memory``, ``file_store``,
  ``journal_memory``, ``memory``, ``search``, ``skills``, ``workspace``.
* ``collaboration`` — ``continuous_control_plane``,
  ``session_command_ledger``, ``session_followup_policy``,
  ``session_persistence``, ``session_projections``,
  ``session_turn_controller``.
* ``journal`` — ``artifact_closure``, ``declarative_runtime_seams``,
  ``fact_store_memory``, ``runtime_factory``.
* ``observability`` — ``attribute_policy``, ``cli_debug_trace``,
  ``event_descriptor``, ``evidence_store_filesystem``,
  ``fact_reader_console``,
  ``fact_reader_langfuse``, ``fact_reader_otel``,
  ``fact_scorer_langfuse``, ``genai_llm``, ``genai_tool``,
  ``tracer_otel``, ``trace_tool``.

Pre-encapsulated subpackages (kept as-is):

* ``event_identity`` — ``stable_ulid``.
* ``journal_schema`` — ``v2``.
* ``openai_stream_encoder`` — ``_chunk``, ``_encoder``.
* ``profile_snapshot`` — ``run_boot``.
* ``run_ui_encoder`` — ``_encoder``.
"""
