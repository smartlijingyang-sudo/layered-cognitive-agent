"""COMPAT(owner: ADR-0195 P3-09, from: handlers/runs/terminal/live_compat, to: read/runs/terminal,
delete_when: rg 'handlers\\.runs\\.terminal\\.live_compat' lca/ tests/ = 0, forbidden_new_usage: yes)
"""

from lca.plugins.transport.webserver.read.runs.terminal.live_compat import *  # noqa: F403
