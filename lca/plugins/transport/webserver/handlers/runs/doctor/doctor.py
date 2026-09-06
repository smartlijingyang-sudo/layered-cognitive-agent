"""COMPAT(owner: ADR-0195 P3-10, from: handlers/runs/doctor/doctor, to: webserver/doctor,
delete_when: rg 'handlers\\.runs\\.doctor\\.doctor' lca/ tests/ = 0, forbidden_new_usage: yes)
"""

from lca.plugins.transport.webserver.doctor.doctor import *  # noqa: F403
