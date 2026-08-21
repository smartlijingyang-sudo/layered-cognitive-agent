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
from lca.contracts.atoms.functional_group import (
    V3_TO_0069_MAPPING,
    FunctionalGroup,
    all_group_ids,
    parse_functional_group,
)
from lca.contracts.atoms.scope import (
    SCOPE_ALIAS,
    Scope,
    all_scope_values,
    canonical_scope,
    parse_scope,
)

__all__ = [
    "SCOPE_ALIAS",
    "SLOT_PHASE_OWNER",
    "V3_TO_0069_MAPPING",
    "ControlSlot",
    "FunctionalGroup",
    "Scope",
    "all_group_ids",
    "all_scope_values",
    "all_slot_values",
    "as_phase_label",
    "canonical_scope",
    "is_cross_cutting",
    "parse_functional_group",
    "parse_scope",
    "parse_slot",
    "phase_owner",
    "validate_slot_iterable",
]
