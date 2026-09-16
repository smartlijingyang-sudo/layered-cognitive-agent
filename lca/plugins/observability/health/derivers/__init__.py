"""Run-health derivers (PR-1 / Task 1.3).

Eight ``HealthDeriver`` implementations, one per PR-1 health dimension:
``perceive``, ``think``, ``act``, ``tool`` (covers sandbox as a sub-rule
per spec §15 G-21), ``llm``, ``reflect``, ``remember``, ``lifecycle``.

Each module is registered via ``pyproject.toml`` under the
``lca.health_derivers`` entry-point group; the fold function in
``lca/plugins/observability/health/run_health_fold.py`` (Task 1.4) loads
them via ``importlib.metadata.entry_points``. No direct imports between
derivers — cross-references go through the shared ``_spine`` helpers.
"""