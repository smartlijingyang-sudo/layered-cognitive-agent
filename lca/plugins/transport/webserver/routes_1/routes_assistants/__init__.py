"""``/v1/assistants`` REST surface (ADR-0187 §3 D7 + PR-5) split into a
focused subpackage.

The package root re-exports the full historical module surface so the path
``lca.plugins.transport.webserver.routes_1.routes_assistants`` keeps working
for bundles, bridge code and tests.
"""

from __future__ import annotations

from lca.plugins.transport.webserver.routes_1.routes_assistants.codecs import (
    _ASSISTANT_JOBS_MARKER,
    _ASSISTANT_NOT_IMPLEMENTED_MARKER,
    _PROFILE_PATCH_FIELDS,
    _bind_ownership,
    _catalog_from_request,
    _error_envelope,
    _extract_emoji,
    _is_dev_mode,
    _jobs_from_request,
    _jobs_not_implemented,
    _json,
    _not_implemented,
    _ownership_error,
    _ownership_from_request,
    _parse_skill_source,
    _profile_patch_from_body,
    _profile_view,
    _register_bridge,
    _skill_overlay_from_request,
    _user_from_request,
)
from lca.plugins.transport.webserver.routes_1.routes_assistants.jobs import (
    assistant_jobs_root,
    create_assistant_job,
    fire_assistant_job,
    list_assistant_jobs,
    run_assistant_job,
    snooze_assistant_job,
)
from lca.plugins.transport.webserver.routes_1.routes_assistants.lobehub import (
    bind_agent,
    import_lobehub_agent,
    register_lobehub,
)
from lca.plugins.transport.webserver.routes_1.routes_assistants.profile import (
    assistants_root,
    create_assistant,
    get_assistant,
    list_assistants,
    reimport_assistant,
    retire_assistant,
    revise_assistant_profile,
)
from lca.plugins.transport.webserver.routes_1.routes_assistants.router import (
    ROUTE_SPECS,
    setup,
)
from lca.plugins.transport.webserver.routes_1.routes_assistants.skills import (
    install_assistant_skill,
)

__all__ = [
    "ROUTE_SPECS",
    "_ASSISTANT_JOBS_MARKER",
    "_ASSISTANT_NOT_IMPLEMENTED_MARKER",
    "_PROFILE_PATCH_FIELDS",
    "_bind_ownership",
    "_catalog_from_request",
    "_error_envelope",
    "_extract_emoji",
    "_is_dev_mode",
    "_jobs_from_request",
    "_jobs_not_implemented",
    "_json",
    "_not_implemented",
    "_ownership_error",
    "_ownership_from_request",
    "_parse_skill_source",
    "_profile_patch_from_body",
    "_profile_view",
    "_register_bridge",
    "_skill_overlay_from_request",
    "_user_from_request",
    "assistant_jobs_root",
    "assistants_root",
    "bind_agent",
    "create_assistant",
    "create_assistant_job",
    "fire_assistant_job",
    "get_assistant",
    "import_lobehub_agent",
    "install_assistant_skill",
    "list_assistant_jobs",
    "list_assistants",
    "register_lobehub",
    "reimport_assistant",
    "retire_assistant",
    "revise_assistant_profile",
    "run_assistant_job",
    "setup",
    "snooze_assistant_job",
]
