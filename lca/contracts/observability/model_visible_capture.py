"""ADR-0169 D7:ModelVisibleCapture —— LLM 边界真实捕获(不在 cursor)。

职责(ADR-0169 D7 + ADR-0170 §D7):
- 在 LLM adapter 边界被调用,一次性写 5 件套(system / tools / messages /
  manifest / inherited)到 ``model_visible/step_<NN>/``。
- 返回 ``ModelVisibleArtifact``(digest + relpath bundle)给调用方,
  由调用方交给 ``cursor.record_request_header(...)`` 落 spine EP。
- cursor 不知道 Capture 存在(评审 S1 处方)。

5 件套契约(ADR-0169 D7 / ADR-0167 I-MV1):
- 每次真实 LLM 请求,必须存在可解析的 ``ModelVisibleArtifact`` 与
  ``llm.request.header`` EP(spine 入口),使得离线可重建
  「当时发给模型的 system / tools / messages」。
- inherited 文件仅在 ``inherited_from_step`` 非 None 时创建
  (对应 ADR-0169 §9 用例表 "checkpoint resume" 路径)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ModelVisibleArtifact:
    """Capture 写盘产物的不可变描述,供 cursor.record_request_header 消费。

    字段语义(ADR-0169 D4 / D7):
    - step_id 由调用方传入(来自 cursor.snapshot.step_id);Capture 不派生。
    - *_digest 是 ``sha256:<hex>`` 形式;cursor 仅持 digest 字符串,不持原内容。
    - *_path 是相对 ``run_dir`` 的 POSIX 风格 relpath;
      解析时由 ``run_dir / path`` 还原。
    - inherited_* 仅当 ``inherited_from_step`` 非 None 时有意义;
      inherited_path 为 None 表示「没有上一 step 可继承」语义(本 step 是初始)。
    """

    step_id: str
    system_path: str
    tools_path: str
    messages_path: str
    manifest_path: str
    inherited_path: str | None
    # Digests 携带给 cursor.record_request_header 写 llm.request.header EP
    system_digest: str
    tools_digest: str
    messages_digest: str
    manifest_digest: str


class ModelVisibleCapture(Protocol):
    """LLM 边界真实捕获 —— 单一职责,不属于 cursor(ADR-0169 D7)。

    实现约束(本 Protocol):
    - 写入 ``<run_dir>/model_visible/step_<NN>/{system,tools,messages,
      manifest,inherited}.json``;inherited 文件仅在
      ``inherited_from_step`` 非 None 时创建。
    - 必须 ``mkdir -p`` 父目录;失败抛 ``OSError``(不静默),由调用方
      决定是否降级到 host 错误指标(ADR-0170 §D7 "失败 fallback 写到
      host 错误指标而非 throw" 是 host 边界;本层不夹带)。
    - 必须用 ``hashlib.sha256`` 派生 digest,统一 ``"sha256:<hex>"`` 形式。
    - 不修改 cursor 内部状态(评审 §7.6;Capture 读取 cursor.snapshot
      但不写它,本 Protocol 把契约钉死)。
    """

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
        """写 5 件套到 model_visible/step_<NN>/,并返回 digest + relpath 打包。

        参数:
            step_id                 : 由 cursor.snapshot 派生(LLM adapter 已知)。
            incarnation             : 同上,纳入 artifact 仅作审计记录,不入 digest。
            system                  : 已渲染的 system prompt —— str 或结构化 dict,
                                      由实现决定 JSON 序列化策略。
            tools                   : 当前可用工具 schema 列表(可能为空)。
            messages                : 实际发给模型的消息序列;序列化时按角色保留。
            manifest                : 上下文 manifest(附件 / 客观 / 记忆种类清单);
                                      由实现选择可 JSON 化字段。
            inherited_from_step     : 前一可继承 step 的 step_id;None ⇒ 本 step
                                      是初始(不写 inherited 文件)。

        返回:
            ``ModelVisibleArtifact``:5 个文件路径 + 4 个 digest。
            调用方负责把这份 artifact 喂给 ``cursor.record_request_header(...)``。
        """
        ...


__all__ = ["ModelVisibleArtifact", "ModelVisibleCapture"]
