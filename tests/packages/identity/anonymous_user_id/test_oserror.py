"""测试 OSError 异常处理分支"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lca.packages.identity.anonymous_user_id import (
    AnonymousUserIdOptions,
    getOrCreateAnonymousUserId,
)
from lca.packages.identity.anonymous_user_id.index import _reset_memo


def test_oserror_during_overwrite():
    """测试并发创建时，尝试覆盖文件时发生 OSError 的情况

    这个测试覆盖 lines 310-313 的异常处理分支：
    - 首次调用 open('x') 时文件已存在（FileExistsError）
    - 读取到的文件内容不是有效的 UUID
    - 尝试用 write_text 覆盖时发生 OSError
    - 应该使用新生成的 UUID 而不抛出异常
    """
    _reset_memo()

    with tempfile.TemporaryDirectory() as tmpdir:
        options = AnonymousUserIdOptions(env={"DSH_HOME": tmpdir})

        # 第一步：先创建一个包含无效 UUID 的文件（模拟并发 winner 写入了损坏数据）
        file_path = Path(tmpdir) / ".anonymous-user-id"
        file_path.write_text("not-a-valid-uuid")

        # 第二步：mock open('x') 抛出 FileExistsError
        original_open = open

        def mock_open_exclusive(file, mode="r", *args, **kwargs):
            if mode == "x" and ".anonymous-user-id" in str(file):
                raise FileExistsError("File exists")
            return original_open(file, mode, *args, **kwargs)

        # 第三步：mock Path.write_text 抛出 OSError（只在覆盖时）
        # 使用 autospec=True 确保保持原始方法签名
        original_write_text = Path.write_text
        write_call_count = [0]

        def mock_write_text(self, data, encoding=None, errors=None, newline=None):
            if ".anonymous-user-id" in str(self):
                write_call_count[0] += 1
                # 第一次调用 write_text 允许（创建文件）
                # 第二次调用 write_text 抛出 OSError（覆盖时）
                if write_call_count[0] > 1:
                    raise OSError("Permission denied")
            return original_write_text(
                self, data, encoding=encoding, errors=errors, newline=newline
            )

        import builtins

        with patch.object(builtins, "open", side_effect=mock_open_exclusive):
            with patch.object(Path, "write_text", autospec=True, side_effect=mock_write_text):
                # 应该能够返回一个 UUID，即使无法覆盖文件
                user_id = getOrCreateAnonymousUserId(options)
                assert user_id  # 应该返回一个有效的 UUID
                # 应该是新生成的 UUID，而不是损坏文件中的内容
                assert user_id != "not-a-valid-uuid"


def test_readonly_home_directory():
    """测试并发创建时，文件系统只读的情况

    这个测试覆盖 lines 316-320 的异常处理分支：
    - 首次调用 open('x') 时发生 OSError（文件系统只读）
    - 应该使用新生成的 UUID 而不抛出异常
    """
    _reset_memo()

    with tempfile.TemporaryDirectory() as tmpdir:
        options = AnonymousUserIdOptions(env={"DSH_HOME": tmpdir})

        # mock open('x') 抛出 OSError
        original_open = open

        def mock_open_readonly(file, mode="r", *args, **kwargs):
            if mode == "x":
                raise OSError("Read-only file system")
            return original_open(file, mode, *args, **kwargs)

        import builtins

        with patch.object(builtins, "open", side_effect=mock_open_readonly):
            # 应该能够返回一个 UUID，即使无法写入文件系统
            user_id = getOrCreateAnonymousUserId(options)
            assert user_id  # 应该返回一个有效的 UUID


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
