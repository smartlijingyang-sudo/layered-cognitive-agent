"""Memory plugins: write policy, compaction, and retrieval backends.

Bundles (base.yaml, scenario-{standard,memgpt,lats,voyager}.yaml) reference
the following module entry points via $module: lca.plugins.memory.X:

- write_policy        (present; exposes Config + setup)
- compaction_policy   (present; exposes Config + setup)
- layered_retrieval   (present; exposes Config)
- four_layer          (MISSING — pre-existing gap, tracked separately)
- tree_cache          (MISSING — pre-existing gap, tracked separately)

Until four_layer and tree_cache are reintroduced, scenarios that
reference them (MemGPT, LATS, Voyager, standard-with-memory) will fail
at profile resolve. This __init__.py restores the package surface so
that ``import lca.plugins.memory`` no longer raises ModuleNotFoundError.
"""

from lca.plugins.memory.compaction_policy import Config as CompactionConfig
from lca.plugins.memory.compaction_policy import setup as setup_compaction
from lca.plugins.memory.layered_retrieval import Config as LayeredRetrievalConfig
from lca.plugins.memory.null_retrieval import Config as NullRetrievalConfig
from lca.plugins.memory.write_policy import Config as WritePolicyConfig
from lca.plugins.memory.write_policy import setup as setup_write_policy

__all__ = [
    "CompactionConfig",
    "LayeredRetrievalConfig",
    "NullRetrievalConfig",
    "WritePolicyConfig",
    "setup_compaction",
    "setup_write_policy",
]
