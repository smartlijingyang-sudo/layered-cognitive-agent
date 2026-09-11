"""CLI command modules — re-export nested command groups for cli.cli."""

from lca.infrastructure.cli.commands.journal import exceptions as journal_exceptions
from lca.infrastructure.cli.commands.journal import journal, replay as journal_replay
from lca.infrastructure.cli.commands.journal import session as journal_session
from lca.infrastructure.cli.commands.journal import step as journal_step
from lca.infrastructure.cli.commands.journal_extra import journal_steps, journal_trace
from lca.infrastructure.cli.commands.kernel import e2e, kernel
from lca.infrastructure.cli.commands.ops import (
    assistants,
    audit,
    composio,
    events_delivery,
    notes,
    typecheck,
)
from lca.infrastructure.cli.commands.profile import (
    creator_plan,
    declarative,
    inspect as profile_inspect,
    package_organization,
)
from lca.infrastructure.cli.commands.runs import (
    diagnostics,
    driver_debug,
    runs,
    services,
    tools,
    workflow,
)

__all__ = [
    "assistants",
    "audit",
    "composio",
    "creator_plan",
    "declarative",
    "diagnostics",
    "e2e",
    "events_delivery",
    "journal",
    "journal_exceptions",
    "journal_replay",
    "journal_session",
    "journal_step",
    "journal_steps",
    "journal_trace",
    "kernel",
    "notes",
    "package_organization",
    "profile_inspect",
    "runs",
    "services",
    "tools",
    "typecheck",
    "workflow",
]
