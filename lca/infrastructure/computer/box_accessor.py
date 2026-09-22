from pathlib import Path

from lca.contracts.models.computer.box import ComputerPlane


class BoxAccessor:
    """员工电脑专属沙箱访问器。

    根据 ADR-0248 §3.2 规定：
    员工电脑（对用户固定称“我的电脑”）是默认工作机，文件系统根目录锚定在 /home/box。
    严禁越出沙箱访问宿主机其它目录。
    """

    def __init__(self, root_dir: str | Path = "/home/box") -> None:
        self.root_dir = Path(root_dir).resolve()
        self.display_name = "我的电脑"
        self.plane = ComputerPlane.BOX

    def resolve_path(self, subpath: str) -> Path:
        """解析并确保路径绝对不越出 /home/box 沙箱根目录。"""
        resolved = (self.root_dir / subpath.lstrip("/")).resolve()
        if not str(resolved).startswith(str(self.root_dir)):
            raise PermissionError(f"越权访问受阻：路径 '{subpath}' 超出员工电脑沙箱范围")
        return resolved

    def write_text(self, subpath: str, content: str) -> Path:
        target = self.resolve_path(subpath)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def read_text(self, subpath: str) -> str:
        target = self.resolve_path(subpath)
        if not target.exists():
            raise FileNotFoundError(f"文件不存在: {subpath}")
        return target.read_text(encoding="utf-8")
