"""COMPAT(owner: ADR-0195 P3-10, from: handlers/runs/doctor/session_check, to: webserver/doctor,
delete_when: rg 'handlers\\.runs\\.doctor\\.session_check' lca/ tests/ = 0, forbidden_new_usage: yes)
"""

from lca.plugins.transport.webserver.doctor.session_check import *  # noqa: F403
