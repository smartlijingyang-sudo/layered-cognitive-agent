"""Path policy seam —— host-fs 写入路径的纯函数校验。

职责
----
契约层唯一入口 :func:`validate_writable_file` —— 在落盘之前,
隔离"输入字符串本身就是错误 (validation)"与"尝试落盘后失败 (execution)"。

被 :mod:`lca.plugins.tools.file_write` 调用;未来任何 host-fs 写入
工具都应优先复用,避免在工具层重复 pattern。

不变式
------
* 纯函数 + 最小副作用:除 :meth:`Path.parent.mkdir` 之外无其它 IO。
* 入参是 :class:`Path`,由调用方负责 :meth:`expanduser` / ``~`` 解析。
* 返回 :class:`PathPolicyDecision`,无异常抛出。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PathPolicyDecision:
    """``validate_writable_file`` 的产出。

    Attributes
    ----------
    accept:
        True 表示路径可用于 host-fs 写入;False 表示拒绝。
    error:
        拒绝时的人类可读理由;接受时为 ``""``。
    failure_kind:
        拒绝时分类。``"validation"`` —— 输入字符串本身就是错误(空串、
        路径指向已存在目录);``"execution"`` —— 输入正常但 parent 创建失败。
        接受时为 ``""``。
    """

    accept: bool
    error: str = ""
    failure_kind: str = ""


def validate_writable_file(path: Path) -> PathPolicyDecision:
    """判定 ``path`` 是否可作为 host-fs 写入目标。

    规则顺序:
    1. 路径字符串为空或仅由空白构成 → 拒绝 (validation)。
    2. ``path`` 已经是一个目录 → 拒绝 (validation)。
    3. 创建父目录时抛出 :class:`OSError` → 拒绝 (execution);
       ``OSError`` 涵盖 :class:`PermissionError` 与
       :class:`FileExistsError`,这一层只做"我们能不能准备写入点"的判断,
       与 retry 策略解耦 —— 分类由 :mod:`lca.cognition.body.safe_executor`
       的 ``_DETERMINISTIC_EXCEPTIONS`` 决定。
    4. 其它情况 → 接受。
    """

    raw = str(path).strip()
    if not raw:
        return PathPolicyDecision(False, "path 不能为空", "validation")
    # Re-resolve via absolute path so an input like "/tmp" classifies as
    # a directory even when path.parent cannot be stat'd.
    try:
        resolved = Path(os.path.abspath(raw))
    except (OSError, ValueError) as exc:
        return PathPolicyDecision(False, f"path 无法解析: {exc}", "validation")
    if resolved.is_dir():
        return PathPolicyDecision(False, f"path 指向已存在的目录: {raw}", "validation")
    parent = resolved.parent
    if not parent.exists():
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return PathPolicyDecision(False, f"无法创建父目录: {exc}", "execution")
    return PathPolicyDecision(True)


__all__ = ["PathPolicyDecision", "validate_writable_file"]
