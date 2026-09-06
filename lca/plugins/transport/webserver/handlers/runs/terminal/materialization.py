"""COMPAT(owner: ADR-0195 P3-08, from: handlers/runs/terminal/materialization, to: read/runs/terminal,
delete_when: rg 'handlers\\.runs\\.terminal\\.materialization' lca/ tests/ = 0, forbidden_new_usage: yes)
"""

from lca.plugins.transport.webserver.read.runs.terminal.materialization import *  # noqa: F403
