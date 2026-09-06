"""COMPAT(owner: ADR-0195 P3-11, from: handlers/runs/wire, to: webserver/wire,
delete_when: rg 'handlers\\.runs\\.wire' lca/ tests/ = 0, forbidden_new_usage: yes)
"""

from lca.plugins.transport.webserver.wire import *  # noqa: F403
