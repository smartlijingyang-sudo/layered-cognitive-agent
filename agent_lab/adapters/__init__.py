"""Adapters — being progressively deleted in fusion refactor (2026-09-08).

Removed:
  - lca_body.py, lca_llm.py, lca_mv.py
  - think parse/gate providers (logic now in nodes/think/*)

Remaining:
  - lca_perceive.py, lca_event.py, lca_memory.py
  - lca_think.py (shared Decision helpers for control only)
  - lca_reflect.py, lca_control.py, lca_control_act.py, lca_toolbox.py
  - tools/read_file.py (kept, agent_lab's own Tool)
"""

__all__: list[str] = []
