"""Session runtime plugin package — COMPAT entry for bundle loader (ADR-0195 P5-02).

``bundles/session-runtime.yaml`` loads ``lca.plugins.session.runtime.plugin``;
canonical ``@plugin`` implementation is ``plugin.plugin``.

# COMPAT(owner: ADR-0195 P5-02, from: runtime/plugin.py flat module,
# to: runtime/plugin/plugin.py,
# delete_when: bundles/session-runtime.yaml $module points at plugin.plugin
#   AND rg "from lca.plugins.session.runtime.plugin import" lca/ tests/ = 0,
# forbidden_new_usage: 新 bundle 条目应指向 runtime.plugin.plugin)
"""

from __future__ import annotations

from lca.plugins.session.runtime.plugin.plugin import Config, setup

__all__ = ["Config", "setup"]
