"""CLI command modules — re-export nested command groups for cli.cli."""

# RA-053: mount the doctor command group on the real root app.
from lca.infrastructure.cli.commands.doctor import profile as doctor_profile
from lca.infrastructure.cli.commands.journal import exceptions as journal_exceptions
from lca.infrastructure.cli.commands.journal import journal
from lca.infrastructure.cli.commands.journal import replay as journal_replay
from lca.infrastructure.cli.commands.journal import session as journal_session
from lca.infrastructure.cli.commands.journal import step as journal_step
from lca.infrastructure.cli.commands.journal_extra import journal_steps, journal_trace
from lca.infrastructure.cli.commands.kernel import e2e, kernel
from lca.infrastructure.cli.commands.ops import (
    assistants,
    audit,
    composio,
    events_delivery,
    memory,
    notes,
    typecheck,
)

# ADR-0221 P3: retired composition/declarative-graph CLI commands are
# not eagerly imported — their modules reference v1 symbols that no
# longer exist. Callers reach them through ``runs create`` /
# ``journal`` workflows which still wire up the kernel.
try:
    from lca.infrastructure.cli.commands.profile import (
        creator_plan,
        declarative,
        package_organization,
    )
    from lca.infrastructure.cli.commands.profile import (
        inspect as profile_inspect,
    )
except ImportError:
    creator_plan = None  # type: ignore[assignment]
    declarative = None  # type: ignore[assignment]
    profile_inspect = None  # type: ignore[assignment]
    package_organization = None  # type: ignore[assignment]
try:
    from lca.infrastructure.cli.commands.runs import (
        driver_debug,
        runs,
        services,
        tools,
        workflow,
    )
except ImportError:
    driver_debug = None  # type: ignore[assignment]
    runs = None  # type: ignore[assignment]
    services = None  # type: ignore[assignment]
    tools = None  # type: ignore[assignment]
    workflow = None  # type: ignore[assignment]

__all__ = [
    "assistants",
    "audit",
    "composio",
    "creator_plan",
    "declarative",
    "doctor_profile",
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
    "memory",
    "notes",
    "package_organization",
    "profile_inspect",
    "runs",
    "services",
    "tools",
    "typecheck",
    "workflow",
]
