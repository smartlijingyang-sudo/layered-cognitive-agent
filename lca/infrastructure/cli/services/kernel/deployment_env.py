"""Resolve a profile against the env the deployed kernel resolves it with.

``lca_kernel serve`` 在 resolve profile 前把白名单过滤后的 ``.env`` 并进
``os.environ``(``lca_kernel/cli/cli.py`` 步骤 1),所以 ``{from_env: ...}``
看到的是 ambient + ``.env`` 两层。lca-ops 的检查跑在自己的进程里,只有 ambient
一层:profile 里任何 ``required: true`` 的 env 引用都会假失败,报告说
"resolve failed" 而 kernel 实际健康。本模块把两层语义补回来,让检查与 boot 同源。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lca.harness.profile.resolve.resolve import ResolvedProfile

__all__ = ["deployment_env", "resolve_profile_with_deployment_env"]


def deployment_env(env_dir: Path | str | None = None) -> dict[str, str]:
    """ambient ``os.environ`` + 白名单过滤后的 ``<env_dir>/.env``。

    ``allow_unknown=True`` 对齐 supervisor spawn 的 ``--allow-unknown-env``:
    未授权 key 不并入,也不让检查比 kernel 更严格。
    """
    from lca_kernel.runtime.env import load_layered_env

    snapshot = load_layered_env(
        bin_name="lca-ops",
        dir=Path.cwd() if env_dir is None else Path(env_dir),
        allow_unknown=True,
    )
    return {**os.environ, **dict(snapshot.dotenv)}


def resolve_profile_with_deployment_env(profile: Path | str) -> ResolvedProfile:
    """``resolve_profile`` 的唯一 out-of-process 入口(检查/诊断路径用)。"""
    from lca.harness.profile.resolve.resolve import resolve_profile

    return resolve_profile(profile, env=deployment_env())
