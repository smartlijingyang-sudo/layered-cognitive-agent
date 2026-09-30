"""Assistant-domain file IO helpers shared by plugins and infrastructure tools.

Consolidates near-verbatim copies of JSON / YAML / grant / digest utilities that
previously lived in ``catalog/plugin.py``, ``assistant/home/_home_layout.py``,
``assistant/persona/persona.py`` and ``tools/assistant/self_manage_tools.py``.
Two JSON error semantics exist on purpose:

- ``read_json`` is strict: non-dict top level raises ``ValueError``
  (manifest / profile faces fail closed).
- ``read_json_soft`` returns ``{}`` on any read/parse error (persona defaults).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import yaml


def read_json(path: Path) -> dict[str, object]:
    """读 JSON 文件；非 dict 抛 ValueError。"""
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: 顶层不是 JSON object")
    return data


def read_json_soft(path: Path) -> dict[str, object]:
    """读 JSON 文件；任何读/解析错误或非 dict 均返回 {}。"""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def write_json(path: Path, data: Mapping[str, object]) -> None:
    """写 JSON 文件（UTF-8 + 缩进 + sort_keys）。"""
    path.write_text(
        json.dumps(dict(data), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


def sha256_digest(path: Path) -> str:
    """计算文件的 ``sha256:<hex>`` 内容 digest。"""
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def load_grants(home: Path) -> frozenset[str]:
    """读 ``grants.yaml`` 的 grant 集合（ADR-0242 D13）。

    缺失 / 损坏 / 非 list 视为空集合（fail-closed 最窄授权）。过滤语义与
    ``lca.plugins.assistant.tools`` 一致。
    """
    path = home / "grants.yaml"
    if not path.is_file():
        return frozenset()
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return frozenset()
    if not isinstance(parsed, dict):
        return frozenset()
    grants = parsed.get("grants")
    if not isinstance(grants, list):
        return frozenset()
    return frozenset(str(item).strip() for item in grants if isinstance(item, str) and item.strip())


__all__ = ["load_grants", "read_json", "read_json_soft", "sha256_digest", "write_json"]
