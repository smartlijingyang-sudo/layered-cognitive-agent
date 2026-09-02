# `loop_cursor/compat/` — Sunset Window

This subpackage centralises every remaining compat surface for the
ADR-0169 / ADR-0173 / ADR-0175 migration cycle. Nothing in this
directory is the canonical implementation; every symbol here is a
re-export from another module, kept here so a single `rg compat/`
shows a complete inventory of legacy paths.

## What's here

| Module | What | Sunset condition |
|---|---|---|
| `coordinator_adapter.py` (via re-export) | `CoordinatorAdapter`, `bind_current_cursor`, `current_cursor`, `get_current_cursor`, `reset_current_cursor` | `rg "coord.begin_step\\|coord.record_thinking\\|coord.emit_phase" lca/cognition lca/body lca/runtime lca/agent` = 0 |
| `bind.py` (via re-export) | `install_run_cursor`, `reset_run_cursor` | `rg "bind_current_cursor\\|get_current_cursor" lca/` = 0 |
| `model_visible_binding.py` (via re-export) | `install_model_visible_capture`, `bind_current_capture`, `reset_current_capture`, `reset_model_visible_capture` | n/a — already thin ContextVar shim |
| `reasoner_prompt_binding.py` (via re-export) | `bind_current_reasoner_prompt`, `get_current_reasoner_prompt`, `install_reasoner_prompt`, `reset_current_reasoner_prompt`, `reset_reasoner_prompt` | n/a — already thin ContextVar shim |

## Sunsetting rule

The day a deletion condition's grep returns zero, the corresponding
file is removed and this README shrinks. Until then: do NOT add new
callers — every new `coord.*` or `bind_*` import extends the sunset
window.
