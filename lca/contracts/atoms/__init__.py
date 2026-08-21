"""atoms — contracts 内部子包（依赖方向由 import-linter 契约强制）。"""

from lca.contracts.atoms.control_slot import (
    SLOT_PHASE_OWNER,
    ControlSlot,
    all_slot_values,
    as_phase_label,
    is_cross_cutting,
    parse_slot,
    phase_owner,
    validate_slot_iterable,
)

__all__ = [
    "SLOT_PHASE_OWNER",
    "ControlSlot",
    "all_slot_values",
    "as_phase_label",
    "is_cross_cutting",
    "parse_slot",
    "phase_owner",
    "validate_slot_iterable",
]
