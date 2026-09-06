# phase_graph — COMPAT shim layer (ADR-0194 G11 / P4-P07)

Legacy import and bundle paths for phase-graph plugins. **SSOT moved to** ``lca/plugins/loop/``:

| Legacy path | SSOT |
|---|---|
| ``phase_graph/standard`` | ``loop/graph/topology/standard/plugin.py`` |
| ``phase_graph/resilient`` | ``loop/graph/resilient/plugin.py`` |
| ``phase_graph/edges_standard`` | ``loop/graph/edges/standard/plugin.py`` |
| ``phase_graph/recovery`` | ``loop/graph/recovery/plugin.py`` |
| ``phase_graph/{perceive,think,act,reflect,remember,stop}`` | ``loop/phase/<phase>/standard/plugin.py`` |
| ``phase_graph/failure_stop`` | ``loop/phase/_shared/failure_stop.py`` |
| ``phase_graph/stop_policy`` | ``phase_graph/stop/policy.py`` (pending ``loop/state/``) |
| ``phase_graph/{registry,agent,aggregator,topology}`` | nested ``*/`` modules (pending ``loop/graph/nodes/``) |

**delete_when:** ``rg 'lca\.plugins\.phase_graph' bundles/`` returns 0 **and** production ``lca/`` imports only COMPAT-free paths.

**forbidden_new_usage:** do not add bundle entries or imports under ``lca.plugins.phase_graph`` except extending this COMPAT layer.
