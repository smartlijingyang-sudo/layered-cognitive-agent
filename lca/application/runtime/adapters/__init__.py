"""L0 wire → RunIntent adapters (ADR-0199 §2.2.1 / P1-08).

These adapters are the only bridge between transport-layer wire objects
(RunRequest, CLI argv) and the wire-agnostic RunIntent contract. They
MUST NOT import starlette / fastapi / argparse — that would leak L0
concerns into the contracts / application boundary.

Per I-HPC-1 the L0 surface's only job is to produce a RunIntent; the
facade in lca.application.runtime is what interprets it.
"""

from lca.application.runtime.adapters.intent_from_cli import (
    CliRunArgs,
    cli_args_to_intent,
)
from lca.application.runtime.adapters.intent_from_transport import (
    run_request_to_intent,
)

__all__ = ("CliRunArgs", "cli_args_to_intent", "run_request_to_intent")
