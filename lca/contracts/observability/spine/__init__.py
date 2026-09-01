"""Spine contracts — seam Protocols for spine plugin authors.

This package holds the data contracts and Protocols that downstream
spine plugins (reflectors, classifiers, derivers) implement. It is
intentionally import-clean per the layer rule:
``lca.contracts.* -> lca.infrastructure.*`` is forbidden, so concrete
types referenced from these Protocols use ``Any`` with a documented
contract in their module docstrings.
"""

from __future__ import annotations

from lca.contracts.observability.spine.producer import (
    FieldProducer as FieldProducer,
)
from lca.contracts.observability.spine.producer import (
    Phase as Phase,
)

__all__ = ["FieldProducer", "Phase"]
