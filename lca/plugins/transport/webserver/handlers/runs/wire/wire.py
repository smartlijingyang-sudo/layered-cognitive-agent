"""COMPAT(owner: ADR-0195 P3-11, from: handlers/runs/wire/wire, to: webserver/wire,
delete_when: rg 'handlers\\.runs\\.wire\\.wire' lca/ tests/ = 0, forbidden_new_usage: yes)
"""

from lca.plugins.transport.webserver.wire.wire import *  # noqa: F403
