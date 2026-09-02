"""ADR-0169 D7:StdModelVisibleCapture —— 默认实现。

职责:
- 一次性写 5 件套到 ``<run_dir>/model_visible/step_<step_id>/{...}.json``
  (system / tools / messages / manifest / inherited)。
- inherited 文件仅在 ``inherited_from_step`` 非 None 时创建
  (对应 ADR-0169 §9 "checkpoint resume" 用例)。
- 返回 ``ModelVisibleArtifact``,由 LLM adapter 边界调用
  ``cursor.record_request_header(...)`` 时消费。

设计要点(评审 S1 处方 + ADR-0169 D7):
- Capture **不持有** cursor 引用 —— 协议边界不夹带。
  调用方(LLM adapter)在捕获时已持有 cursor.snapshot,
  把 step_id / incarnation 作为参数传入。
- 仅依赖 stdlib:hashlib / json / pathlib。
- 序列化策略:任意可序列化对象用 ``json.dumps(... default=str)`` 保底,
  对 Pydantic / dataclass 实例由 ``__dict__`` 退化为 dict。
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path, PurePosixPath
from typing import Any

from lca.contracts.observability.model_visible_capture import (
    ModelVisibleArtifact,
    ModelVisibleCapture,
)

_log = logging.getLogger(__name__)

_DIGEST_PREFIX = "sha256:"
"""digest 字符串前缀,与 step_tree_accumulator._write_model_visible 保持一致。"""


def _to_jsonable(value: Any) -> Any:
    """把任意对象转成可 JSON 序列化的结构。

    优先级:
    1. 已是 dict / list / str / int / float / bool / None ⇒ 原样;
    2. 有 ``to_dict`` / ``model_dump`` / ``dict()`` 协议 ⇒ 调用之;
    3. 有 ``__dict__`` ⇒ 取之;
    4. 兜底 ``repr(value)``。

    保证 ``json.dumps(...)`` 不抛 TypeError。
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    # Pydantic v2 / dataclass 等有 to_dict/model_dump/dict 接口 —— 顺次尝试,失败退路
    for proto_name in ("to_dict", "model_dump", "dict"):
        proto = getattr(value, proto_name, None)
        if callable(proto):
            try:
                return _to_jsonable(proto())
            except Exception as exc:
                _log.debug("model_visible %s() failed: %s", proto_name, exc)
    if hasattr(value, "__dict__"):
        try:
            return _to_jsonable(vars(value))
        except Exception as exc:
            _log.debug("model_visible vars() failed: %s", exc)
    return repr(value)


def _sha256_digest(payload: Any) -> str:
    """算 ``sha256:<hex>`` —— 与 step_tree_accumulator 兼容格式。"""
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return _DIGEST_PREFIX + hashlib.sha256(encoded).hexdigest()


def _relative_posix(run_dir: Path, target: Path) -> str:
    """算相对 ``run_dir`` 的 POSIX 风格 relpath。

    失败(跨盘 / 越界)退化为 target.name —— 不抛,以保 cursor
    record_request_header 永不因路径计算而抛异常。
    """
    try:
        rel = target.relative_to(run_dir)
    except ValueError:
        return target.name
    return PurePosixPath(rel.as_posix()).as_posix()


def _write_json(path: Path, payload: Any) -> str:
    """写 JSON 到 ``path``(mkdir parents);返回 sha256 digest。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    jsonable = _to_jsonable(payload)
    serialized = json.dumps(
        jsonable,
        ensure_ascii=False,
        indent=2,
        default=str,
        sort_keys=False,
    )
    path.write_text(serialized, encoding="utf-8")
    return _sha256_digest(jsonable)


class StdModelVisibleCapture(ModelVisibleCapture):
    """默认 ModelVisibleCapture 实现。

    用法::

        capture = StdModelVisibleCapture(run_dir=Path("traces/runs/<run_id>"))
        artifact = capture.capture(
            step_id="step-007",
            incarnation=1,
            system={"role": "system", "content": "..."},
            tools=[{"name": "echo"}, ...],
            messages=[{"role": "user", "content": "hi"}],
            manifest={"objective": "...", "kinds": ["objective"]},
            inherited_from_step="step-006",  # 可选
        )
        cursor.record_request_header(RequestHeader(
            ...,
            system_digest=artifact.system_digest,
            system_path=artifact.system_path,
            ...
        ))

    写入位置(ADR-0169 D7)::
        <run_dir>/model_visible/<step_id>/system.json
        <run_dir>/model_visible/<step_id>/tools.json
        <run_dir>/model_visible/<step_id>/messages.json
        <run_dir>/model_visible/<step_id>/manifest.json
        <run_dir>/model_visible/<step_id>/inherited.json   # 当 inherited_from_step 非 None
    """

    def __init__(self, *, run_dir: Path) -> None:
        self._run_dir = Path(run_dir)

    @property
    def run_dir(self) -> Path:
        """返回注入的 run_dir。"""
        return self._run_dir

    def capture(
        self,
        *,
        step_id: str,
        incarnation: int,
        system: Any,
        tools: list[Any],
        messages: list[Any],
        manifest: Any,
        inherited_from_step: str | None = None,
    ) -> ModelVisibleArtifact:
        # 路径就位:<run_dir>/model_visible/<step_id>/
        step_dir = self._run_dir / "model_visible" / step_id

        # 4 个必写文件(顺序无关,但保持 system → tools → messages → manifest)
        system_path = step_dir / "system.json"
        tools_path = step_dir / "tools.json"
        messages_path = step_dir / "messages.json"
        manifest_path = step_dir / "manifest.json"

        # 系统提示,常含元信息:incarnation + step_id 在 manifest 里而非 system 里
        system_with_meta = {
            "incarnation": incarnation,
            "step_id": step_id,
            "body": _to_jsonable(system),
        }
        system_digest = _write_json(system_path, system_with_meta)

        tools_digest = _write_json(tools_path, _to_jsonable(tools))
        messages_digest = _write_json(messages_path, _to_jsonable(messages))
        manifest_with_meta = {
            "incarnation": incarnation,
            "step_id": step_id,
            "body": _to_jsonable(manifest),
        }
        manifest_digest = _write_json(manifest_path, manifest_with_meta)

        # inherited:仅当 inherited_from_step 非 None 时写
        inherited_path: Path | None = None
        if inherited_from_step is not None:
            inherited_path = step_dir / "inherited.json"
            _write_json(
                inherited_path,
                {
                    "inherited_from_step": inherited_from_step,
                    "incarnation": incarnation,
                    "step_id": step_id,
                },
            )

        return ModelVisibleArtifact(
            step_id=step_id,
            system_path=_relative_posix(self._run_dir, system_path),
            tools_path=_relative_posix(self._run_dir, tools_path),
            messages_path=_relative_posix(self._run_dir, messages_path),
            manifest_path=_relative_posix(self._run_dir, manifest_path),
            inherited_path=(
                _relative_posix(self._run_dir, inherited_path)
                if inherited_path is not None
                else None
            ),
            system_digest=system_digest,
            tools_digest=tools_digest,
            messages_digest=messages_digest,
            manifest_digest=manifest_digest,
        )


__all__ = ["StdModelVisibleCapture"]
