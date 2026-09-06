"""COMPAT(owner: ADR-0195 P3-10, from: handlers/runs/doctor, to: webserver/doctor,
delete_when: rg 'handlers\\.runs\\.doctor' lca/ tests/ = 0, forbidden_new_usage: yes)
"""

from lca.plugins.transport.webserver.doctor import *  # noqa: F403
