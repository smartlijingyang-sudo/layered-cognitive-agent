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
"""digest 字符串前缀,与 ADR-0169 D4 / ADR-0176 D2 兼容格式。"""


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

    写入位置(ADR-0169 D7 + ADR-0176 D4):
        <run_dir>/model_visible/<step_id>/tools.json
        <run_dir>/model_visible/<step_id>/messages.json  # messages_overview.system + messages[]
        <run_dir>/model_visible/<step_id>/manifest.json
        <run_dir>/model_visible/<step_id>/inherited.json   # 当 inherited_from_step 非 None
        # 注:system_prompt.json / system_prompt_sections.json 由 StdReasonerPromptCapture 写,
        #   不再由本 Capture 写。system 数据合并到 messages.json 的 messages_overview.system 区段。
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

        # ADR-0176 D4:删除 system.json(系统提示合并到 messages.json 的
        # messages_overview.system 区段);tools / messages / manifest 三个文件保留。
        tools_path = step_dir / "tools.json"
        messages_path = step_dir / "messages.json"
        manifest_path = step_dir / "manifest.json"

        tools_digest = _write_json(tools_path, _to_jsonable(tools))

        # messages.json 现在承载两件事:
        # - messages_overview.system:送入 LLM 的 system 段(原 system.json 数据)
        # - messages:实际发给模型的消息序列
        messages_payload: dict[str, Any] = {
            "incarnation": incarnation,
            "step_id": step_id,
            "messages_overview": {
                "system": _to_jsonable(system),
            },
            "messages": _to_jsonable(messages),
        }
        messages_digest = _write_json(messages_path, messages_payload)

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

        # ADR-0176 D4:system_path 不再指向独立 system.json,而是 messages.json
        # 的 messages_overview.system 区段;前端 viewer 据此找到完整 system 上下文。
        # COMPAT(delete-when: 所有调用方已迁移到 system_path 指向 messages.json,
        # tracking: ADR-0176 D4)
        return ModelVisibleArtifact(
            step_id=step_id,
            system_path=_relative_posix(self._run_dir, messages_path),
            tools_path=_relative_posix(self._run_dir, tools_path),
            messages_path=_relative_posix(self._run_dir, messages_path),
            manifest_path=_relative_posix(self._run_dir, manifest_path),
            inherited_path=(
                _relative_posix(self._run_dir, inherited_path)
                if inherited_path is not None
                else None
            ),
            # system_digest 复用 messages_digest;调用方需要时仍可读 system 段
            # 的 content_digest。本字段保留 Protocol 兼容性。
            system_digest=messages_digest,
            tools_digest=tools_digest,
            messages_digest=messages_digest,
            manifest_digest=manifest_digest,
        )


__all__ = ["StdModelVisibleCapture"]
