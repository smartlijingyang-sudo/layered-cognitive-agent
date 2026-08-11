"""Parse sandbox stderr into structured, agent-actionable summaries (ADR-0050)."""

from __future__ import annotations

import re

from lca.contracts.models.core.sandbox import SandboxErrorKind, SandboxResult

_USER_LINE_RE = re.compile(
    r'File "<lca-user>", line (\d+)',
)
_FLOAT_NOT_ITERABLE_RE = re.compile(
    r"TypeError: argument of type 'float' is not iterable",
)
_FILE_NOT_FOUND_RE = re.compile(
    r"FileNotFoundError: \[Errno 2\] No such file or directory: '([^']+)'"
)
_KEY_ERROR_RE = re.compile(r"KeyError: '([^']+)'")
_MODULE_NOT_FOUND_RE = re.compile(r"ModuleNotFoundError: No module named '([^']+)'")
_SURROGATE_ENCODE_RE = re.compile(r"UnicodeEncodeError.*surrogates not allowed")


def classify_execution_error(
    result: SandboxResult,
) -> tuple[SandboxErrorKind, str, str, int | None, bool]:
    """Return (kind, summary, suggested_fix, failed_at_line, partial)."""
    stderr = result.stderr or ""
    stdout = result.stdout or ""
    partial = bool(stdout.strip()) and not result.success

    line_match = _USER_LINE_RE.search(stderr)
    failed_at_line = int(line_match.group(1)) if line_match else None

    if _FILE_NOT_FOUND_RE.search(stderr):
        path = _FILE_NOT_FOUND_RE.search(stderr)
        guest_path = path.group(1) if path else "unknown"
        return (
            SandboxErrorKind.USER_CODE,
            f"FileNotFoundError: {guest_path}",
            (
                "路径不存在。先用 list_files 查看 /mnt/data；"
                "写入前 os.makedirs(os.path.dirname(path), exist_ok=True) 或使用 write_file(createDirectories=true)；"
                "产出文件应写到 /mnt/data/outputs/"
            ),
            failed_at_line,
            partial,
        )

    if _FLOAT_NOT_ITERABLE_RE.search(stderr):
        return (
            SandboxErrorKind.USER_CODE,
            "TypeError: 对 float/NaN 使用了 'in' 或迭代 — 常见于 Excel 空单元格",
            "对列使用 series.dropna().astype(str) 后再做字符串操作",
            failed_at_line,
            partial,
        )

    if _KEY_ERROR_RE.search(stderr):
        key = _KEY_ERROR_RE.search(stderr)
        col = key.group(1) if key else "?"
        return (
            SandboxErrorKind.USER_CODE,
            f"KeyError: 列/键 '{col}' 不存在",
            "用 list_files / read_file 查看实际数据结构，不要猜测列名",
            failed_at_line,
            partial,
        )

    if _MODULE_NOT_FOUND_RE.search(stderr):
        mod = _MODULE_NOT_FOUND_RE.search(stderr)
        name = mod.group(1) if mod else "?"
        return (
            SandboxErrorKind.USER_CODE,
            f"ModuleNotFoundError: {name}",
            f"预装包见工具描述；{name} 不在 baseline 中",
            failed_at_line,
            partial,
        )

    err_blob = (result.error or "") + stderr
    if _SURROGATE_ENCODE_RE.search(err_blob):
        return (
            SandboxErrorKind.USER_CODE,
            "UnicodeEncodeError: matplotlib/stdout 含非法 surrogate 字符",
            "图表保存用 plt.savefig(..., format='png') 而非 print；中文标签用 fontproperties 或英文标签",
            failed_at_line,
            partial,
        )

    if "timed out" in stderr.lower() or "timeout" in (result.error or "").lower():
        return (
            SandboxErrorKind.TIMEOUT,
            result.error or "执行超时",
            "减小数据量或提高 timeout_s",
            failed_at_line,
            partial,
        )

    if stderr.strip():
        first_line = stderr.strip().splitlines()[-1]
        return (
            SandboxErrorKind.USER_CODE,
            first_line[:240],
            "",
            failed_at_line,
            partial,
        )

    return (
        SandboxErrorKind.INFRA,
        result.error or "sandbox execution failed",
        "",
        failed_at_line,
        partial,
    )
