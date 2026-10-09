from pathlib import Path

import pytest

from lca.contracts.models.computer.box import ComputerPlane
from lca.infrastructure.computer.box_accessor import BoxAccessor


def test_computer_plane_enum():
    assert ComputerPlane.BOX == "box"
    assert ComputerPlane.LOCAL == "local"


def test_box_accessor_sandbox_isolation(tmp_path: Path):
    box_root = tmp_path / "home_box"
    box_root.mkdir()
    accessor = BoxAccessor(root_dir=box_root)

    # 合法子路径
    safe_path = accessor.resolve_path("workspace/code.py")
    assert str(safe_path).startswith(str(box_root))

    # 试图越权逃逸
    with pytest.raises(PermissionError):
        accessor.resolve_path("../../etc/passwd")


def test_box_accessor_read_write(tmp_path: Path):
    box_root = tmp_path / "home_box"
    box_root.mkdir()
    accessor = BoxAccessor(root_dir=box_root)

    accessor.write_text("hello.txt", "hello box computer")
    content = accessor.read_text("hello.txt")
    assert content == "hello box computer"
    assert accessor.display_name == "我的电脑"
    assert accessor.plane == ComputerPlane.BOX
def test_box_accessor_rejects_sibling_prefix_escape(tmp_path: Path):
    """RA-081: /home/box2/evil 相对 /home/box 是兄弟目录。

    str.startswith 做边界检查会误判为界内（真漏洞）；relative_to 语义必须拒绝。
    """
    box_root = tmp_path / "box"
    box_root.mkdir()
    sibling = tmp_path / "box2"
    sibling.mkdir()
    accessor = BoxAccessor(root_dir=box_root)

    with pytest.raises(PermissionError):
        accessor.resolve_path("../box2/evil.txt")
