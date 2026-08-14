"""Guest-side artifact harvest constants.

Re-exports ``ARTIFACT_BEGIN`` / ``ARTIFACT_END`` markers used by
``strip_artifacts`` to parse generated-file blocks from sandbox stdout.
"""

from __future__ import annotations

from lca.layer0_infra.sandbox.onlyboxes_artifacts import ARTIFACT_BEGIN, ARTIFACT_END
from lca.layer0_infra.sandbox.paths import ONLYBOXES

# Guest Python executed after user code to scan the outputs directory and
# print an artifact marker block that the host parses via ``strip_artifacts``.
GUEST_ARTIFACT_SCANNER: str = f"""
import os as _os, json as _json, base64 as _b64, mimetypes as _mt
try:
    _scan_files = []
    _output_dir = {ONLYBOXES.outputs_dir!r}
    if _os.path.isdir(_output_dir):
        for _fname in sorted(_os.listdir(_output_dir)):
            # Skip workspace markers / hidden ops files (e.g. .workspace-initialized).
            if not _fname or _fname.startswith("."):
                continue
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
