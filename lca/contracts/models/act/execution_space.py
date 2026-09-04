"""ExecutionSpace —— G2 空间事实的最小投影（ADR-0187 §3 D5 + design 2026-08-21）。

``ExecutionSpace`` 是 Agent 实际能触达的计算环境的 typed 投影；本模块提供
PR-4 助理域使用的最小 dataclass 形态，仅覆盖 cwd 根 + ACL allowlist + backend
来源 + parent space id 五字段。设计文档
``docs/design/2026-08-21-spacetime-governed-creator-runtime.md`` §2.2 列出
10 字段形态（``space_id`` / ``backend`` / ``workspace`` / ``outputs`` /
``device_ref`` / ``network_zone`` / ``capabilities`` / ``filesystem_policy_ref``
/ ``egress_policy_ref`` / ``env_baseline_ref`` / ``parent_space_id``），
是 SpacetimeContext 子空间的实现目标，本模块不预先铺张。

Precondition：所有路径字段为绝对路径字符串；``acl_paths`` 元素必须 ⊆
``workspace_path`` 子树（构造期校验，违反 = ``ValueError``）。

Failure：不变量违反 ⇒ ``ValueError``；catalog + workspace plugin 不持有可变
引用，只读消费。

时序：run 期由 ``assistant.workspace`` plugin
(:mod:`lca.plugins.assistant.workspace`) 物化；不在 boot 期物化（助理是
run 期动态创建的数据，0088 钉 boot vs run 边界）。

所有权：ExecutionSpace dataclass 由 contracts 层冻结；实例构造后不可变。
世界写仍走既有 Body / CommandEnvelope（G7）—— ExecutionSpace 不是 effect
入口，是 effect 在空间上的**事实**。
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass


def _normalize_path(path: str) -> str:
    """绝对路径化（不解析符号链接；构造期 sanity check）。"""
    if not path or not path.strip():
        raise ValueError("ExecutionSpace 路径字段必须为非空字符串")
    expanded = os.path.expanduser(path)
    if not os.path.isabs(expanded):
        raise ValueError(f"ExecutionSpace 路径必须是绝对路径，得到 {expanded!r}")
    return expanded


@dataclass(frozen=True, slots=True)
class ExecutionSpace:
    """最小 G2 空间事实（PR-4 助理域使用）。

    字段：

    - ``space_id`` —— 该 ExecutionSpace 的唯一标识（PR-4 用 ``assistant_id`` 派生）
    - ``backend`` —— backend 类别；PR-4 固定 ``"local"``
    - ``workspace_path`` —— cwd 根；助理工具默认 ``workspace_only=true``（I-A5）
    - ``acl_paths`` —— 允许触达的可读 / 可写子树白名单；构造期校验 ⊆ ``workspace_path``
    - ``parent_space_id`` —— 父 space（profile scope 或 None）
    """

    space_id: str
    backend: str
    workspace_path: str
    acl_paths: tuple[str, ...] = ()
    parent_space_id: str | None = None

    def __post_init__(self) -> None:
        if not self.space_id or not self.space_id.strip():
            raise ValueError("ExecutionSpace.space_id 必须为非空字符串")
        if not self.backend or not self.backend.strip():
            raise ValueError("ExecutionSpace.backend 必须为非空字符串")
        normalized_workspace = _normalize_path(self.workspace_path)
        if normalized_workspace != self.workspace_path:
            object.__setattr__(self, "workspace_path", normalized_workspace)
        normalized_acl: list[str] = []
        workspace_prefix = normalized_workspace.rstrip(os.sep) + os.sep
        for raw in self.acl_paths:
            normalized = _normalize_path(raw)
            if not (normalized == normalized_workspace or normalized.startswith(workspace_prefix)):
                raise ValueError(
                    f"ExecutionSpace.acl_paths 项 {normalized!r} 不在 workspace_path "
                    f"{normalized_workspace!r} 子树内（I-A5 隔离硬边界）"
                )
            normalized_acl.append(normalized)
        if not isinstance(self.acl_paths, tuple):
            object.__setattr__(self, "acl_paths", tuple(normalized_acl))
        else:
            object.__setattr__(self, "acl_paths", tuple(normalized_acl))


def materialize_assistant_workspace(
    *,
    assistant_id: str,
    home_path: str,
    acl_paths: Iterable[str] | None = None,
    parent_space_id: str | None = None,
) -> ExecutionSpace:
    """从 AssistantHome 物化 ExecutionSpace（PR-4 助理域 helper）。

    - ``space_id`` = ``"asstspace:" + assistant_id``
    - ``workspace_path`` = ``{home_path}/workspace/``（绝对路径）
    - ``backend`` = ``"local"``
    - ``acl_paths`` 缺省 = 仅 ``workspace_path``；显式传入则 ⊆ workspace 子树
    - ``parent_space_id`` = profile 级 space（assistant 助理域父 = profile）
    """
    normalized_home = _normalize_path(home_path)
    workspace_path = normalized_home.rstrip(os.sep) + os.sep + "workspace"
    acl = tuple(acl_paths) if acl_paths is not None else (workspace_path,)
    return ExecutionSpace(
        space_id=f"asstspace:{assistant_id}",
        backend="local",
        workspace_path=workspace_path,
        acl_paths=acl,
        parent_space_id=parent_space_id,
    )


__all__ = ["ExecutionSpace", "materialize_assistant_workspace"]
