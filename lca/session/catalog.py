"""Session event catalog public API (ADR-0195 P1-04).

Known-type closure and read-path fail-closed validation. Implementation remains
in ``lca.plugins.session.runtime.event_catalog`` until Wave P4 lift.
"""

from __future__ import annotations

from lca.plugins.session.runtime.event_catalog import (
    UnknownSessionEventTypeError,
    known_session_event_types,
    validate_event_type_for_read,
)

__all__ = [
    "UnknownSessionEventTypeError",
    "known_session_event_types",
    "validate_event_type_for_read",
]
