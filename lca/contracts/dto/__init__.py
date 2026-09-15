"""Typed DTOs that cross the declarative-graph boundary.

Crossing a typed-boundary node (think / act / intervene / delegate) every
output port must be a Pydantic frozen model with ``extra="forbid"``
(ADR-0195 §1.4 / ADR-0219 §5.5 / C13). New typed ports land here.
"""
