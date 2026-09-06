from __future__ import annotations

import pytest

from lca.contracts.harness.act.sandbox_limits import SandboxResourceLimits


def test_sandbox_limits_allow_bounded_output_file() -> None:
    limits = SandboxResourceLimits(max_files=2, max_file_bytes=100)

    assert limits.allows_file(100, 1) is True
    assert limits.allows_file(100, 2) is False
    assert limits.allows_file(101, 0) is False


@pytest.mark.parametrize("kwargs", [{"timeout_s": 0}, {"max_files": -1}, {"max_file_bytes": -1}])
def test_sandbox_limits_reject_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        SandboxResourceLimits(**kwargs)
