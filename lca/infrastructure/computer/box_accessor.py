import os
import uuid
from pathlib import Path
from typing import Any

from lca.contracts.models.computer.box import ComputerPlane


class BoxAccessor:
    """员工电脑专属沙箱访问器。

    根据 ADR-0248 §3.2 规定：
    员工电脑（对用户固定称“我的电脑”）是默认工作机，文件系统根目录锚定在 /home/box。
    严禁越出沙箱访问宿主机其它目录。
    """

    def __init__(
        self,
        root_dir: str | Path = "/home/box",
        adapter: Any | None = None,
    ) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.display_name = "我的电脑"
        self.plane = ComputerPlane.BOX
        if adapter is not None:
            self.adapter = adapter
            self.root_dir = getattr(adapter, "root_dir", self.root_dir)
        else:
            from lca.infrastructure.computer.box_sandbox_adapter import LocalBoxAdapter

            self.adapter = LocalBoxAdapter(root_dir=self.root_dir)
            self.root_dir = getattr(self.adapter, "root_dir", self.root_dir)

    def resolve_path(self, subpath: str) -> Path:
        """解析并确保路径绝对不越出 /home/box 沙箱根目录。"""
        resolved = (self.root_dir / subpath.lstrip("/")).resolve()
        if not str(resolved).startswith(str(self.root_dir)):
            raise PermissionError(f"越权访问受阻：路径 '{subpath}' 超出员工电脑沙箱范围")
        return resolved

    def write_text(self, subpath: str, content: str) -> Path:
        target = self.resolve_path(subpath)
        target.parent.mkdir(parents=True, exist_ok=True)
        # ADR-0251 决策一：原子刷盘（临时文件落地 + fsync + 原子 os.replace）
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
        return target

    def read_text(self, subpath: str) -> str:
        target = self.resolve_path(subpath)
        if not target.exists():
            raise FileNotFoundError(f"文件不存在: {subpath}")
        return target.read_text(encoding="utf-8")
