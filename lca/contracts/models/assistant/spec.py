"""AssistantSpec —— 助理 Home 解析的冻结视图（ADR-0187 §3 D3）。

``AssistantSpec`` 是助理域的 SSOT 视图：``resolve`` 后产出，构造 AgentSpec
形状的同一管线（ADR-0088 RuntimeFactory）消费。frozen dataclass 不允许原地
变更；任何配置调整都必须经 ``Catalog.revise_profile`` 或
``Catalog.reimport`` 重新 resolve，避免运行时旁路写配置。

三类真值分层在助理域的体现（ADR-0187 §3 D2 / I-A13）：

| 面 | 字段 | 变更机制 |
|---|---|---|
| 配置（digest SSOT） | profile / bootstrap.* / grant / tools policy / skill index | revise / reimport ⇒ digest + revision_seq++ |
| 记忆 | （不在本 spec，memory seam 各自记） | memory seam，不进 digest |
| 运行事实 | （不在本 spec） | Spine / Journal（ADR-0167） |

``revision_seq`` 是助理配置修订计数（与 ADR-0169 ``Incarnation.incarnation_seq``
正交，不复用同一词），用于 EP payload 携带修订快照。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from lca.contracts.models.assistant.plan_overlay import PlanOverlay

if TYPE_CHECKING:
    from lca.contracts.protocols.journal.spec.spec import AgentSpec


@dataclass(frozen=True)
class AssistantBootstrapRefs:
    """bootstrap 配置面三个文件的 content digest。

    SOUL / USER / AGENTS 是 resolve 期的 digest 校验锚点；
    MEMORY.md 属追加真值，不参与 digest 与 ``revision_seq``（ADR-0187 §3 D2
    真值分层 + I-A13）。IDENTITY.md 已删除（身份信息由 profile.json SSOT 拥有）。
    """

    soul_digest: str
    user_digest: str
    agents_digest: str

    def __post_init__(self) -> None:
        for name, value in (
            ("soul_digest", self.soul_digest),
            ("user_digest", self.user_digest),
            ("agents_digest", self.agents_digest),
        ):
            if not value or not value.strip():
                raise ValueError(f"{name} 必须为非空 content digest 字符串")


@dataclass(frozen=True)
class AssistantSpec:
    """助理域 SSOT 冻结视图（ADR-0187 §3 D3）。

    一切使一个 assistant 区别于另一个 assistant 的配置都是 Home 数据
    （ADR-0242 D9）：``profile_model`` / ``profile_locale`` /
    ``profile_runtime`` 与 name/description 一样来自 ``profile.json``，
    运行时与全局配置只提供默认值。

    Precondition：
      - ``assistant_id`` 非空；
      - ``revision_seq >= 0``；
      - ``agent_spec`` 已通过 ADR-0033 声明式构造；
      - ``bootstrap`` 四个 digest 全部已计算；
      - ``grant_digest`` 与 ``tools_policy_digest`` 与 Home 的 ``grants.yaml`` /
        ``tools.yaml`` 内容一致（resolve 期校验；运行期不可重新计算）。

    Failure：构造不变量违反 ⇒ ``ValueError``；resolve 期 digest 不匹配 ⇒ Catalog
    失败（fail-closed，由 Catalog 调用方抛出）。

    时序：Catalog 解析 Home ⇒ 校验 manifest 配置面 digest ⇒ 产 ``AssistantSpec``
    （含 ``manifest_digest`` 与 ``plan_overlay``）⇒ 与
    ``(assistant_id, manifest_digest)`` 一起缓存 CompiledRunPlan。

    Ownership：助理域 SSOT 由 ``AssistantCatalog`` 持有；运行期 Runtime 不持有
    可变引用，只读消费 dataclass 字段。

    外部后果：``AssistantSpec`` 是运行期唯一允许携带 ``agent_spec`` 进
    ``Resolve → Compile`` 管线的输入。绕过 ``Catalog`` 自行构造（拼装 manifest /
    注入配置）违反 ADR-0187 §6 删除条件「**无**平行 AgentSpec 编译器」。
    """

    assistant_id: str
    home_path: str
    revision_seq: int
    template_id: str
    profile_name: str
    profile_description: str
    agent_spec: AgentSpec  # ADR-0033 核心，复用不平行
    bootstrap: AssistantBootstrapRefs
    skill_ids: tuple[str, ...]
    job_ids: tuple[str, ...]
    grant_digest: str
    tools_policy_digest: str
    grants: frozenset[str] = field(default_factory=frozenset)
    """``grants.yaml`` 的 grant 集合（ADR-0242 D13）。

    未来 ``assistant.invoke``（multi-agent 编排）直接用它校验目标 assistant
    的授权，无需再解析 Home。与 ``grant_digest`` 同源：digest 是配置面校验锚，
    本字段是运行期可直接使用的集合。"""
    role_id: str | None = None
    """创建时引用的角色档案 role_id（如 'engineering/engineering-software-architect'）。
    None 表示用模板默认 SOUL 创建。"""
    profile_opening_message: str = ""
    """profile.json 的 ``opening_message``（ADR-0242 D9）；空 = 未配置。"""
    profile_locale: str = ""
    """profile.json 的 ``locale``（ADR-0242 D9）；空 = 未配置（默认 zh-CN 由模板提供）。"""
    profile_model: str = ""
    """profile.json 的 ``model``（ADR-0242 D9）；空 = 使用运行时/全局默认模型。"""
    profile_runtime: dict[str, object] = field(default_factory=dict)
    """profile.json 的 ``runtime``（ADR-0242 D9）；空 dict = 运行参数全部用默认值。"""
    manifest_digest: str = ""
    """manifest.json 的 ``manifest_digest``；与 ``(assistant_id, manifest_digest)``
    一起作为 CompiledRunPlan 缓存键（ADR-0242 D10 / I-B10）。"""
    plan_overlay: PlanOverlay | None = None
    """``{home}/plan.yaml`` 解析出的覆盖（ADR-0242 D10）。

    None = Home 无 plan.yaml（旧助理）或文件为空覆盖；非 None 时进入
    Resolve → Compile 管线的 per-agent plan 合并（L3 编译）。"""

    def __post_init__(self) -> None:
        if not self.assistant_id or not self.assistant_id.strip():
            raise ValueError("assistant_id 必须为非空字符串")
        if not self.home_path or not self.home_path.strip():
            raise ValueError("home_path 必须为非空路径字符串")
        if self.revision_seq < 0:
            raise ValueError(f"revision_seq 必须为非负整数，得到 {self.revision_seq!r}")
        if not self.template_id or not self.template_id.strip():
            raise ValueError("template_id 必须为非空模板标识")
        if not self.grant_digest or not self.grant_digest.strip():
            raise ValueError("grant_digest 必须为非空 content digest")
        if not self.tools_policy_digest or not self.tools_policy_digest.strip():
            raise ValueError("tools_policy_digest 必须为非空 content digest")


__all__ = ["AssistantBootstrapRefs", "AssistantSpec"]
