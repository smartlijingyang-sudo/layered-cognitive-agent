"""Spine event records — ``Channel`` literal and the ``Outcome`` close-set.

``Outcome`` is defined in :mod:`lca.contracts.observability.evidence.outcome`;
it is re-exported here so spine-contract consumers can import the whole
event vocabulary from one package.
"""

from __future__ import annotations

from typing import Literal

from lca.contracts.observability.evidence.outcome import Outcome as Outcome

__all__ = ["Channel", "Outcome"]

Channel = Literal["fact", "control", "error", "diagnostic"]
