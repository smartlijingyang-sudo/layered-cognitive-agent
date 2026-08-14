"""Computer use constants — guest markers and result caps.

Sandbox disk roots live in ``lca.layer0_infra.sandbox.paths``.
"""

from __future__ import annotations

# Guest JSON marker for structured computer op results.
COMPUTER_RESULT_BEGIN = "__LCA_COMPUTER__"
COMPUTER_RESULT_END = "__END_COMPUTER__"

# Max lines returned by read_file without explicit range.
READ_FILE_DEFAULT_MAX_LINES = 500

# Max grep / glob / search results.
MAX_GREP_MATCHES = 200
MAX_GLOB_RESULTS = 1000
MAX_SEARCH_RESULTS = 200

# Streaming tools — journal projector emits live stdout for these wire API names.
STREAMING_WIRE_APIS = frozenset({"runCommand", "executeCode", "execScript"})
