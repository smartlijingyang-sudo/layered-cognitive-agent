"""passthrough — stateless 1-in-1-out workers.

Two coexisting implementations (skeleton period, 2026-09-08):
  - Legacy: identity / select / redact / dedup / rank / constant
            (factory = short name; used by existing graphs/configs/*.yaml)
  - Skeleton v2: identity_v2 / select_v2 / redact_v2 / dedup_v2 / rank_v2 / prefix_v2
            (factory = passthrough__<worker>; used by new graphs/<phase>/<phase>.yaml)

Migration: rename legacy yaml factories to passthrough__<worker>, then
delete the legacy files. Until then both sets are registered.
"""
# Legacy (do not remove until graphs/configs/*.yaml migrate):
from agent_lab.nodes.passthrough.identity.plugin import Identity
from agent_lab.nodes.passthrough.select.plugin import Select
from agent_lab.nodes.passthrough.redact.plugin import Redact
from agent_lab.nodes.passthrough.dedup.plugin import Dedup
from agent_lab.nodes.passthrough.rank.plugin import Rank
# constant has no plugin.py in legacy; skip if absent
try:
    from agent_lab.nodes.passthrough.constant.plugin import Constant  # noqa: F401
except ImportError:
    pass

# Skeleton v2 (new canonical names):
from agent_lab.nodes.passthrough.identity_v2.plugin import Identity as IdentityV2
from agent_lab.nodes.passthrough.select_v2.plugin import Select as SelectV2
from agent_lab.nodes.passthrough.redact_v2.plugin import Redact as RedactV2
from agent_lab.nodes.passthrough.dedup_v2.plugin import Dedup as DedupV2
from agent_lab.nodes.passthrough.rank_v2.plugin import Rank as RankV2
from agent_lab.nodes.passthrough.prefix_v2.plugin import Prefix as PrefixV2

__all__ = [
    # Legacy
    "Identity", "Select", "Redact", "Dedup", "Rank",
    # v2
    "IdentityV2", "SelectV2", "RedactV2", "DedupV2", "RankV2", "PrefixV2",
]
