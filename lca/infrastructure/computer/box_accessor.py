from pathlib import Path

from lca.contracts.models.computer.box import ComputerPlane
from lca.infrastructure.computer.box_gate import (
    atomic_write_text,
    contain_path,
    resolve_box_root,
)


class BoxAccessor:
    """员工电脑专属沙箱访问器。

    根据 ADR-0248 §3.2 规定：
    员工电脑（对用户固定称"我的电脑"）是默认工作机，文件系统根目录锚定在 /home/box。
    严禁越出沙箱访问宿主机其它目录。

    安全边界（路径 containment、原子刷盘）收敛在 box_gate：
    本类只做同步工具路径的薄调用。
    """

    def __init__(self, root_dir: str | Path = "/home/box") -> None:
        # RA-081：删掉 vestigial 的 adapter 参数/懒导入（全树零读取）；
        # 根目录回退解析收敛到 box_gate.resolve_box_root。
        self.root_dir = resolve_box_root(root_dir)
        self.display_name = "我的电脑"
        self.plane = ComputerPlane.BOX

    def resolve_path(self, subpath: str) -> Path:
        """解析并确保路径绝对不越出沙箱根目录。"""
        return contain_path(self.root_dir, subpath)

    def write_text(self, subpath: str, content: str) -> Path:
        target = self.resolve_path(subpath)
        target.parent.mkdir(parents=True, exist_ok=True)
        # ADR-0251 决策一：原子刷盘收敛到 box_gate.atomic_write_text
        atomic_write_text(target, content)
        return target

    def read_text(self, subpath: str) -> str:
        target = self.resolve_path(subpath)
        if not target.exists():
            raise FileNotFoundError(f"文件不存在: {subpath}")
        return target.read_text(encoding="utf-8")
