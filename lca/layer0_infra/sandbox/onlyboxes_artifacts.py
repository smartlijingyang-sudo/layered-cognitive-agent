"""Onlyboxes stdout artifact harvest block (ADR-0046 companion)."""

from __future__ import annotations

import base64
import json
import re

from lca.contracts.models.core.sandbox import SandboxFile
from lca.layer0_infra.sandbox.output_collect import try_append_generated_file

ARTIFACT_BEGIN = "__LCA_ONLYBOXES_ARTIFACTS__"
ARTIFACT_END = "__END_LCA_ARTIFACTS__"
_ARTIFACT_RE = re.compile(
    re.escape(ARTIFACT_BEGIN) + r"(.+?)" + re.escape(ARTIFACT_END),
    re.DOTALL,
)


def strip_artifacts(stdout: str) -> tuple[str, list[SandboxFile], list[str]]:
    """Remove artifact block from stdout; return cleaned text + files + diags."""
    generated: list[SandboxFile] = []
    diagnostics: list[str] = []
    match = _ARTIFACT_RE.search(stdout)
    if not match:
        return stdout, generated, diagnostics
    cleaned = stdout[: match.start()] + stdout[match.end() :]
    cleaned = cleaned.rstrip() + ("\n" if stdout.endswith("\n") or cleaned else "")
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        diagnostics.append(f"[lca] artifact json parse failed: {exc}\n")
        return cleaned, generated, diagnostics
    if not isinstance(payload, list):
        diagnostics.append("[lca] artifact payload is not a list\n")
        return cleaned, generated, diagnostics
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        b64s = str(item.get("b64") or "")
        if not name or not b64s:
            continue
        try:
            data = base64.b64decode(b64s)
        except (ValueError, TypeError) as exc:
            diagnostics.append(f"[lca] bad b64 for {name!r}: {exc}\n")
            continue
        if not try_append_generated_file(generated, diagnostics, name=name, data=data):
            break
    return cleaned, generated, diagnostics
