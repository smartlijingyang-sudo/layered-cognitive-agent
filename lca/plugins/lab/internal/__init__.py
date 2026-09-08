"""Internal helpers for the LCA lab plugin family.

PR-A.2 — hook helper 私有化；本模块仅供 lca.plugins.lab.* plugin 与
agent_lab graph/compile / runtime/runner 在过渡期使用；PR-A.3 后
graph/compile.py / runtime/runner.py 改用 lca.plugins.lab.internal.hooks。

Public consumers must not import from this package directly. The symbols
here are wired into the @plugin setup() / runner / compiler paths; they
are not a stable API surface.
"""
