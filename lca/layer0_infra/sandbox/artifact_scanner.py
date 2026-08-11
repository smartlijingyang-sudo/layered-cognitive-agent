"""Guest-side artifact harvest script (ADR-0046).

Injected after ``execute_code`` user code so ``/mnt/data/outputs`` files are
collected via the stdout marker parsed by ``onlyboxes_artifacts.strip_artifacts``.
"""

from __future__ import annotations

import textwrap

from lca.layer0_infra.sandbox.bootstrap import sandbox_output_path
from lca.layer0_infra.sandbox.onlyboxes_artifacts import ARTIFACT_BEGIN, ARTIFACT_END

# Guest Python executed in a ``finally`` block after user code.
GUEST_ARTIFACT_SCANNER: str = f"""
import os as _os, json as _json, base64 as _b64, mimetypes as _mt
try:
    _scan_files = []
    _output_dir = {sandbox_output_path()!r}
    if _os.path.isdir(_output_dir):
        for _fname in sorted(_os.listdir(_output_dir)):
            _fpath = _os.path.join(_output_dir, _fname)
            if _os.path.isfile(_fpath):
                try:
                    with open(_fpath, "rb") as _fh:
                        _raw = _fh.read()
                    _scan_files.append({{
                        "name": _fname,
                        "b64": _b64.b64encode(_raw).decode(),
                        "mime_type": _mt.guess_type(_fname)[0] or "application/octet-stream",
                    }})
                except OSError:
                    pass
    if _scan_files:
        print({ARTIFACT_BEGIN!r} + _json.dumps(_scan_files) + {ARTIFACT_END!r})
except Exception:
    pass
""".strip()


def wrap_code_with_artifact_scanner(code: str) -> str:
    """Wrap user Python so outputs under ``/mnt/data/outputs`` are harvested."""
    return (
        "try:\n"
        + textwrap.indent(code, "    ")
        + "\nfinally:\n"
        + textwrap.indent(GUEST_ARTIFACT_SCANNER, "    ")
    )
