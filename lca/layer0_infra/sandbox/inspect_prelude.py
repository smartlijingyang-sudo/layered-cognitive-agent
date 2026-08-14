"""Guest-side inspect script — lists the sandbox root and profiles tabular files (ADR-0050)."""

from __future__ import annotations

from lca.contracts.models.core.sandbox import SANDBOX_OUTPUT_SUBDIR
from lca.layer0_infra.sandbox.paths import ONLYBOXES

INSPECT_SCRIPT = """
import json as _j
import os as _o
root = __SANDBOX_ROOT__
out = {"files": [], "profiles": {}}
for dirpath, _, filenames in _o.walk(root):
    if "/__OUTPUTS_SUBDIR__" in dirpath.replace("\\\\", "/"):
        continue
    for fn in filenames:
        fp = _o.path.join(dirpath, fn)
        rel = _o.path.relpath(fp, root)
        try:
            size = _o.path.getsize(fp)
        except OSError:
            size = 0
        out["files"].append({"path": fp, "name": fn, "relative": rel, "size_bytes": size})
        lower = fn.lower()
        if lower.endswith((".xlsx", ".xls")):
            try:
                import pandas as pd
                xl = pd.ExcelFile(fp)
                sheets = {}
                for s in xl.sheet_names:
                    df = xl.parse(s)
                    nan_rows = int(df.isna().all(axis=1).sum())
                    cols = [str(c) for c in df.columns.tolist()]
                    sample_rows = df.head(3).to_dict(orient="records")
                    sheets[s] = {
                        "rows": int(len(df)),
                        "columns": cols,
                        "column_count": len(cols),
                        "nan_rows": nan_rows,
                        "dtypes": {str(k): str(v) for k, v in df.dtypes.items()},
                        "sample": sample_rows,
                    }
                out["profiles"][fn] = {"type": "excel", "sheets": sheets}
            except Exception as exc:
                out["profiles"][fn] = {"type": "excel", "error": str(exc)}
        elif lower.endswith((".doc",)):
            out["profiles"][fn] = {
                "type": "legacy_word",
                "hint": "旧版 Word .doc（OLE2）；优先转 docx 后用 officecli；或 olefile 探测",
                "suggested_skills": [],
            }
        elif lower.endswith((".docx",)):
            try:
                import docx as _docx
                doc = _docx.Document(fp)
                paras = [p.text for p in doc.paragraphs if p.text.strip()]
                out["profiles"][fn] = {
                    "type": "docx",
                    "paragraphs": len(paras),
                    "preview": paras[:3],
                    "hint": "Office 编辑优先 officecli（activate_skill officecli + run_command）",
                }
            except Exception as exc:
                out["profiles"][fn] = {"type": "docx", "error": str(exc)}
        elif lower.endswith((".pptx",)):
            out["profiles"][fn] = {
                "type": "pptx",
                "hint": "PowerPoint；activate_skill('officecli') 后 run_command 调用 officecli",
            }
        elif lower.endswith(".pdf"):
            out["profiles"][fn] = {"type": "pdf", "hint": "PDF 输入；可用 pypdf 读取或 anthropics-skills-pdf 生成"}
        elif lower.endswith(".csv"):
            try:
                import pandas as pd
                df = pd.read_csv(fp, nrows=5)
                full = pd.read_csv(fp)
                out["profiles"][fn] = {
                    "type": "csv",
                    "rows": int(len(full)),
                    "columns": [str(c) for c in full.columns.tolist()],
                    "sample": df.head(3).to_dict(orient="records"),
                }
            except Exception as exc:
                out["profiles"][fn] = {"type": "csv", "error": str(exc)}
print("__LCA_INSPECT__" + _j.dumps(out, ensure_ascii=False) + "__END_INSPECT__")
""".replace("__SANDBOX_ROOT__", repr(ONLYBOXES.root)).replace(
    "__OUTPUTS_SUBDIR__", SANDBOX_OUTPUT_SUBDIR
)

INSPECT_BEGIN = "__LCA_INSPECT__"
INSPECT_END = "__END_INSPECT__"


def parse_inspect_stdout(stdout: str) -> dict[str, object] | None:
    """Extract inspect JSON payload embedded in guest stdout."""
    start = stdout.find(INSPECT_BEGIN)
    end = stdout.find(INSPECT_END)
    if start < 0 or end < 0 or end <= start:
        return None
    import json

    raw = stdout[start + len(INSPECT_BEGIN) : end]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
