"""员工电脑沙箱边界门（ADR-0248 §3.2 / s04，ADR-0251 决策一）。

沙箱安全 invariant 的唯一 owner：路径 containment、原子刷盘、提权硬闸。
BoxAccessor（同步工具路径，走生产流量）与 LocalBoxAdapter /
OnlyboxesBoxAdapter（异步 port 实现）都只是这座门的薄调用方——
安全规则改一处，三处生效；测试钉住生产路径。

历史教训（RA-081）：containment 曾有两份实现且正确性分叉——
BoxAccessor 用 str.startswith 做边界检查，/home/box2/evil 相对 /home/box
是兄弟目录却被误判为界内（前缀逃逸真漏洞）；正确的 relative_to 实现
躺在生产不用的 adapter 里。收敛后只有 relative_to 语义。
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path


def resolve_box_root(root_dir: str | Path) -> Path:
    """解析沙箱根目录：尽力创建；无权限时回退到 LCA_BOX_ROOT / lca home 下的 box。"""
    root = Path(root_dir).resolve()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        from lca.infrastructure.path.locator import get_lca_home

        fallback = Path(os.environ.get("LCA_BOX_ROOT", get_lca_home() / "box"))
        fallback.mkdir(parents=True, exist_ok=True)
        root = fallback.resolve()
    return root


def contain_path(root_dir: Path, subpath: str) -> Path:
    """把 subpath 解析进沙箱根目录；越界抛 PermissionError。

    必须用 relative_to 语义，绝不用 str.startswith：/home/box2/evil
    相对 /home/box 是兄弟目录，startswith 会误判为界内。
    """
    target = (root_dir / subpath.lstrip("/")).resolve()
    try:
        target.relative_to(root_dir)
    except ValueError:
        raise PermissionError(
            f"越权访问受阻：路径 '{subpath}' 超出员工电脑沙箱范围 ({root_dir})"
        ) from None
    return target


def atomic_write_text(target: Path, content: str) -> None:
    """ADR-0251 决策一：原子刷盘（临时文件落地 + fsync + 原子 os.replace）。"""
    tmp_target = target.parent / f".tmp_{target.name}_{uuid.uuid4().hex[:8]}"
    try:
        with tmp_target.open("w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_target, target)
    except BaseException:
        if tmp_target.exists():
            tmp_target.unlink()
        raise


def check_no_privilege_escalation(command: str) -> None:
    """INV-04 安全硬闸：员工电脑沙箱禁止 sudo/su 等提权命令。"""
    cmd_stripped = command.strip()
    if (
        cmd_stripped.startswith("sudo ")
        or cmd_stripped.startswith("su ")
        or " sudo " in command
        or " su " in command
    ):
        raise PermissionError("安全硬闸：员工电脑沙箱禁止提权命令 (sudo/su)")


__all__ = [
    "atomic_write_text",
    "check_no_privilege_escalation",
    "contain_path",
    "resolve_box_root",
]
