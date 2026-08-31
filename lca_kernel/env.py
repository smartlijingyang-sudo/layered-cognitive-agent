"""K7:分层 env 加载 facade。

Public surface
--------------
- :class:`EnvSnapshot` —— 不可变 env 快照(ambient + filtered .env + 状态)。
- :func:`load_layered_env` —— 读取 ``<dir>/.env``,按白名单过滤,返回
  :class:`EnvSnapshot`。

Architecture
------------
本模块把 :mod:`lca.infrastructure.env` 暴露的三个常量 + filter 函数
组合成 kernel 层的 facade:

- :func:`load_layered_env` 是唯一调用 ``os.environ`` + 读 ``.env`` 的位置。
- :class:`EnvSnapshot` 是 frozen dataclass;plugin 通过
  ``ctx.inject("env")`` 拿到 immutable provenance。
- 不读 ``python-dotenv``(用 stdlib 解析,避免引入额外依赖,见
  :func:`_read_dotenv`)。

迁移来源
--------
ADR-0117 §决定 5(K7 load 函数签名)+ ADR-0115 决定 1 K7。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from lca.infrastructure.env.bootstrap import (
    BOOTSTRAP_FORBIDDEN,
    BOOTSTRAP_NAMES,
    BOOTSTRAP_PREFIXES,
)
from lca.infrastructure.env.layered import filter_env_keys
from lca_kernel.errors import KernelError


@dataclass(frozen=True, slots=True)
class EnvSnapshot:
    """Immutable env snapshot: ambient + filtered .env + diagnostic sets.

    - ``ambient`` —— 启动时的 ``os.environ``(只读映射)。
    - ``dotenv`` —— 经过白名单过滤后的 ``.env`` 条目(只读映射)。
    - ``allowed_keys`` —— 实际允许从 ``.env`` 加载的 key 集合。
    - ``blocked_keys`` —— 被拒绝的 key 集合(fail-loud 触发源)。
    """

    ambient: MappingProxyType
    dotenv: MappingProxyType
    allowed_keys: frozenset[str]
    blocked_keys: frozenset[str]


def load_layered_env(
    bin_name: str,
    dir: Path | str | None = None,
    *,
    allow_unknown: bool = False,
) -> EnvSnapshot:
    """读取 ``.env``,按白名单过滤,返回 frozen :class:`EnvSnapshot`。

    三层模型(借鉴 deepseek ``app-boot/src/index.ts:loadLayeredEnv``):

    - Layer 0:ambient ``os.environ``(启动时冻结,只读)。
    - Layer 1:``<dir>/.env``(按 :data:`~lca.infrastructure.env.bootstrap.BOOTSTRAP_NAMES`
      + :data:`~lca.infrastructure.env.bootstrap.BOOTSTRAP_PREFIXES` 过滤)。
    - Layer 2:profile env refs(由 ADR-0061 §决定 2 ``{from_env: ...}`` 引用,
      已在 :mod:`lca_kernel.declarations` 展开;此处不重复处理)。

    Parameters
    ----------
    bin_name:
        诊断前缀(用于错误信息)。
    dir:
        读取 ``.env`` 的目录;默认 ``Path.cwd()``。
    allow_unknown:
        默认 ``False``(fail-loud);``True`` 时跳过 :class:`KernelError`
        检查,把 blocked key 仅作诊断保留。

    Returns
    -------
    EnvSnapshot
        frozen;plugin 通过 ``ctx.inject("env")`` 拿到 immutable provenance。

    Raises
    ------
    KernelError
        当 ``.env`` 含未授权 key 且 ``allow_unknown=False`` 时,带
        ``{bin_name}: blocked env keys in .env: [...]`` 信息。
    """
    if dir is None:
        dir = Path.cwd()
    directory = Path(dir)
    ambient = MappingProxyType(os.environ)
    raw = _read_dotenv(directory / ".env")
    allowed, blocked = filter_env_keys(raw, ambient)
    if blocked and not allow_unknown:
        # Sort blocked by name for deterministic diagnostics.
        blocked_sorted = sorted(blocked)
        raise KernelError(f"{bin_name}: blocked env keys in .env: {blocked_sorted}")
    filtered = MappingProxyType({k: raw[k] for k in allowed})
    return EnvSnapshot(
        ambient=ambient,
        dotenv=filtered,
        allowed_keys=allowed,
        blocked_keys=blocked,
    )


def _read_dotenv(path: Path) -> dict[str, str]:
    """Minimal stdlib ``.env`` reader(K7 不依赖 python-dotenv)。

    格式:
        - ``KEY=VALUE`` 一行一个条目。
        - 空行 / ``#`` 开头跳过。
        - 不支持引号转义(简化);首次 ``=`` 之前的部分作为 key。

    Returns
    -------
    dict[str, str]
        解析得到的条目;文件缺失时返回空字典(``.env`` 可选)。
    """
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def bootstrap_constants() -> tuple[frozenset[str], tuple[str, ...], frozenset[str]]:
    """Return ``(BOOTSTRAP_NAMES, BOOTSTRAP_PREFIXES, BOOTSTRAP_FORBIDDEN)``.

    Convenience accessor for diagnostic tooling — keeps the kernel surface
    thin without re-exporting every constant.
    """
    return BOOTSTRAP_NAMES, BOOTSTRAP_PREFIXES, BOOTSTRAP_FORBIDDEN


__all__ = [
    "BOOTSTRAP_FORBIDDEN",
    "BOOTSTRAP_NAMES",
    "BOOTSTRAP_PREFIXES",
    "EnvSnapshot",
    "bootstrap_constants",
    "load_layered_env",
]


def _ensure_mapping_imported() -> None:  # pragma: no cover
    """Touch Mapping import so the type checker treats it as part of the API."""
    return None


_ = (Mapping,)
