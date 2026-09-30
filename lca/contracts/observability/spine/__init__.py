"""Spine contracts — seam Protocols for spine plugin authors.

This package holds the data contracts and Protocols that downstream
spine plugins (reflectors, classifiers, derivers) implement. It is
intentionally import-clean per the layer rule:
``lca.contracts.* -> lca.infrastructure.*`` is forbidden, so concrete
types referenced from these Protocols use ``Any`` with a documented
contract in their module docstrings.
"""

from __future__ import annotations

from lca.contracts.observability.spine.context import (
    PhaseMachineViolation as PhaseMachineViolation,
)
from lca.contracts.observability.spine.context import (
    PhaseMachineViolationError as PhaseMachineViolationError,
)
from lca.contracts.observability.spine.context import (
    SpanContext as SpanContext,
)
from lca.contracts.observability.spine.context import (
    SpineContext as SpineContext,
)
from lca.contracts.observability.spine.ports import EventSpine as EventSpine
from lca.contracts.observability.spine.producer import (
    FieldProducer as FieldProducer,
)
from lca.contracts.observability.spine.producer import Phase as Phase
from lca.contracts.observability.spine.records import Channel as Channel
from lca.contracts.observability.spine.records import Outcome as Outcome

__all__ = [
    "Channel",
    "EventSpine",
    "FieldProducer",
    "Outcome",
    "Phase",
    "PhaseMachineViolation",
    "PhaseMachineViolationError",
    "SpanContext",
    "SpineContext",
]
