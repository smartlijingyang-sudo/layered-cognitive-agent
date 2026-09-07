"""Wire-parity guard: LCA agent-gateway WS URL SSOT.

PR-3 (commit 975416f0) shipped a `lcaConnectToGateway` that delegated
to the upstream `AgentStreamClient`. The upstream `buildWsUrl()`
hard-codes `<base>/ws?operationId=...`, which is the lobehub-native
gateway wire path. LCA's server-side WS path is locked by ADR-0200 §1
in
  lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/routes.py
  WS_PATH = "/v1/runs/{run_id}/ws"

The two paths never matched; chat silently fell back to the native
`/webapi/chat/<provider>` dispatch in `streamingExecutor.ts` and the
LCA WS code path was never actually exercised.

This test fails if any of these stop being aligned:

  - WS_PATH literal in routes.py.
  - The `/v1/runs/{run_id}/ws` literal in `LcaAgentStreamClient.ts`
    (the only LCA TS file allowed to emit that URL).
  - No new code path imports or constructs the upstream
    `AgentStreamClient` inside `lcaGateway/*`. This is also caught by
    `scripts/audit_lca_legacy_path.py`, but a duplicate guard here
    surfaces the SSOT-violating commit even before the audit script
    is run.

If you intentionally need to change WS_PATH, touch both files in the
same PR and add a one-line note in the corresponding Agent Note.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

LCA_WS_PATH = "/v1/runs/{run_id}/ws"


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_server_side_ws_path_matches_ssr_literal() -> None:
    """Server-side WS_PATH in routes.py must equal the SSOT literal."""
    rel = (
        "lca/plugins/transport/webserver/handlers/runs/"
        "terminal/streaming/wire/routes.py"
    )
    text = _read(rel)
    match = re.search(r'^\s*WS_PATH:\s*str\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match is not None, f"WS_PATH declaration not found in {rel}"
    assert match.group(1) == LCA_WS_PATH, (
        f"server WS_PATH drifted from SSOT: {match.group(1)!r} != {LCA_WS_PATH!r}"
    )


def test_lca_agent_stream_client_emits_ssr_url() -> None:
    """LCA's WS client must emit the SSOT URL literal.

    Allowed: one occurrence of `/v1/runs/` inside
    LcaAgentStreamClient.ts (the WS_PATH_TEMPLATE constant).
    Any new occurrence outside that file is a violation.
    """
    rel = "lobehub-ui/src/store/chat/agents/transports/lcaGateway/LcaAgentStreamClient.ts"
    text = _read(rel)
    occurrences = re.findall(r"/v1/runs/", text)
    assert occurrences, (
        f"{rel} no longer references /v1/runs/ — WS client lost its SSR alignment"
    )


def test_lca_gateway_does_not_value_import_upstream_agent_stream_client() -> None:
    """The `import { AgentStreamClient } from '@lobechat/agent-gateway-client'`
    trap that bit PR-3 must not come back.

    `import type { AgentStreamEvent, ... }` is allowed: those mirror the
    wire schema and have no path-pinning. The bug is value-importing
    the class because its `buildWsUrl()` hard-codes the wrong wire
    path.
    """
    lca_gateway_dir = (
        REPO_ROOT / "lobehub-ui/src/store/chat/agents/transports/lcaGateway"
    )
    offenders: list[str] = []
    for ts_file in sorted(lca_gateway_dir.glob("*.ts")):
        text = ts_file.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            # `import type { ... AgentStreamEvent ... }` is fine; value
            # import of AgentStreamClient class is not. Match an import
            # statement that lists AgentStreamClient without `type`.
            if not stripped.startswith("import"):
                continue
            if not re.search(r"\bAgentStreamClient\b", line):
                continue
            # Exclude LCA's own client (`LcaAgentStreamClient`) and the
            # patch-source mirror under deploy/lobehub/patches/.
            if re.search(r"\bLcaAgentStreamClient\b", line):
                continue
            if "type " in stripped or stripped.startswith("import type"):
                continue
            offenders.append(f"{ts_file}:{lineno}: {line}")
    assert not offenders, (
        "value import of upstream AgentStreamClient in lcaGateway/* is forbidden — "
        "use LcaAgentStreamClient instead.\nOffenders:\n  - "
        + "\n  - ".join(offenders)
    )
