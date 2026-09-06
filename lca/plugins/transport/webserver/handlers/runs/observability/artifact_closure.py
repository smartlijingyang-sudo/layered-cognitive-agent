"""COMPAT(owner: ADR-0195 P3-07, from: handlers/runs/observability, to: read/runs,
delete_when: rg 'handlers\\.runs\\.observability' lca/ tests/ = 0, forbidden_new_usage: yes)
"""

from lca.plugins.transport.webserver.read.runs.artifact_closure import *  # noqa: F403
