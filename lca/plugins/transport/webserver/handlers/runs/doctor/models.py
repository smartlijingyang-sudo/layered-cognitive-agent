"""COMPAT(owner: ADR-0195 P3-10, from: handlers/runs/doctor/models, to: webserver/doctor,
delete_when: rg 'handlers\\.runs\\.doctor\\.models' lca/ tests/ = 0, forbidden_new_usage: yes)
"""

from lca.plugins.transport.webserver.doctor.models import *  # noqa: F403
