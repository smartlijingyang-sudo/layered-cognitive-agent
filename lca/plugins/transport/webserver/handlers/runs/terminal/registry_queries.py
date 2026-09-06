"""COMPAT(owner: ADR-0195 P3-09, from: handlers/runs/terminal/registry_queries, to: read/runs/terminal,
delete_when: rg 'handlers\\.runs\\.terminal\\.registry_queries' lca/ tests/ = 0, forbidden_new_usage: yes)
"""

from lca.plugins.transport.webserver.read.runs.terminal.registry_queries import *  # noqa: F403
