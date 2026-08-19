"""精确测试 OSError 异常处理分支（lines 310-313）"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lca.packages.identity.anonymous_user_id import (
    AnonymousUserIdOptions,
    getOrCreateAnonymousUserId,
)
from lca.packages.identity.anonymous_user_id.index import _reset_memo


def test_oserror_when_overwriting_corrupt_file():
    """精确测试 lines 310-313：覆盖损坏文件时发生 OSError

    执行路径：
    1. 文件已存在且内容损坏（不是有效的 UUID）
    2. 首次调用 open('x') 时抛出 FileExistsError
    3. _read_persisted_id 返回 None（因为文件内容无效）
    4. 尝试用 write_text 覆盖时抛出 OSError
    5. 应该捕获 OSError 并使用新生成的 UUID
    """
    _reset_memo()

    with tempfile.TemporaryDirectory() as tmpdir:
        options = AnonymousUserIdOptions(env={"DSH_HOME": tmpdir})

        # 第一步：创建一个包含无效 UUID 的文件
        file_path = Path(tmpdir) / ".anonymous-user-id"
        file_path.write_text("not-a-valid-uuid")

        # 第二步：mock open('x') 抛出 FileExistsError
        original_open = open

        def mock_open_exclusive(file, mode="r", *args, **kwargs):
            if mode == "x" and ".anonymous-user-id" in str(file):
                raise FileExistsError("File exists")
            return original_open(file, mode, *args, **kwargs)

        # 第三步：mock Path.write_text 在调用时抛出 OSError
        # 由于文件已存在且 open('x') 会抛出 FileExistsError，
        # 代码会进入异常处理，然后尝试用 write_text 覆盖
        original_write_text = Path.write_text

        def mock_write_text_with_oserror(self, data, encoding=None, errors=None, newline=None):
            if ".anonymous-user-id" in str(self):
                # 直接抛出 OSError，模拟覆盖失败
                raise OSError("Permission denied during overwrite")
            return original_write_text(
                self, data, encoding=encoding, errors=errors, newline=newline
            )

        import builtins

        with (
            patch.object(builtins, "open", side_effect=mock_open_exclusive),
            patch.object(
                Path, "write_text", autospec=True, side_effect=mock_write_text_with_oserror
            ),
        ):
            # 应该能够返回一个 UUID，即使无法覆盖文件
            user_id = getOrCreateAnonymousUserId(options)

            # 验证：应该返回一个有效的 UUID（不是损坏文件中的内容）
            assert user_id != "not-a-valid-uuid"
            # 验证：返回的是一个有效的 UUID 格式
            import re

            uuid_pattern = re.compile(
                r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
            )
            assert uuid_pattern.match(user_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
