"""AssistantSkillOverlay Protocol —— 助理域 skill overlay（ADR-0187 §3 D4 / D6）。

薄门面：仅暴露 install / list_installed / activate 三个动作。架构约束：

1. **只写本助理 ``{home}/skills/``**；**禁止**写全局 ``~/.lca/skills/``。
   拉取与格式校验复用 ADR-0048 的 ``SkillImporter`` / ``SkillPackageInstaller``
   机制，但安装接缝绑定到本助理 Home 的 staging/落点，不触达全局 store。
2. **未验证包不可 activate**：install 路径必经 ADR-0067 三闸
   （identity / invariant / experiment）并走 ``DRAFT → VERIFIED`` 状态机迁移；
   任一闸失败 ⇒ 不写 Home、不发 EP（fail-closed）。
3. **不因安装扩权**：外部包携带的脚本仍受沙箱与既有 grant 约束；
   安装产生的 artifact ``grants`` 恒为空。
4. **EP 四件套**：install ⇒ ``assistant.skill.installed``，
   activate ⇒ ``assistant.skill.activated``；payload 必含
   ``assistant_id`` / ``revision_seq`` / ``manifest_digest`` / ``actor``。

与 ``SkillAcquirer``（``lca/plugins/skill/auto_acquire.py``，capability
``learning.skill_acquirer``）的关系：后者是全局 candidate-only 缝，不落盘；
本 Protocol 是助理域安装/激活面，落点 = 本助理 Home，capability 独立
（``assistant.skill_overlay``）。进化提案（``assistant.evolve``）是
``SkillAcquirer`` 的助理域对应物，与本 Protocol 不共用实现类。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from lca.contracts.atoms.artifact_state import parse_artifact_state

__all__ = [
    "AssistantSkillOverlay",
    "SkillActivationReceipt",
    "SkillInstallReceipt",
    "SkillNotInstalled",
    "SkillNotVerified",
    "SkillSource",
]


# ── SkillSource：安装源 ──────────────────────────────────────────────


@dataclass(frozen=True)
class SkillSource:
    """``install`` 的安装源；``url`` 与 ``local_path`` 恰好一个非空。

    - ``url`` —— HTTP(S) 链接；实际拉取走 ADR-0048
      ``SkillImporter.import_from_url``（host allowlist、大小上限、
      ZIP 安全解压均由该机制执行）。
    - ``local_path`` —— 本地 skill 目录绝对路径（必含 ``SKILL.md``）；
      不走网络；读取与校验仍经 0048 ``SkillPackageInstaller.install_package``。

    Precondition：两者恰好一个非空；``url`` 必为 ``http(s)://`` 前缀；
    ``local_path`` 必为绝对路径。违反 ⇒ ``ValueError``。
    """

    url: str = ""
    local_path: str = ""

    def __post_init__(self) -> None:
        if bool(self.url.strip()) == bool(self.local_path.strip()):
            raise ValueError("SkillSource 必须且只能指定 url / local_path 之一")
        if self.url.strip():
            if not self.url.startswith(("http://", "https://")):
                raise ValueError(f"SkillSource.url 必为 http(s):// 前缀,得到 {self.url!r}")
        else:
            if not self.local_path.startswith("/"):
                raise ValueError(f"SkillSource.local_path 必为绝对路径,得到 {self.local_path!r}")

    @property
    def reference(self) -> str:
        """非空载体字面（url 或 local_path），供 EP / manifest 溯源。"""
        return self.url if self.url.strip() else self.local_path


# ── 回执 ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SkillInstallReceipt:
    """``install`` 的不可变回执（ADR-0187 §3 D8 四件套 + 包元数据）。

    ``artifact_state`` 取 ``ArtifactState`` 闭集值；``install`` 成功路径
    恒为 ``"verified"``（0067 三闸通过后的状态）。``list_installed`` 扫盘
    时,未经闸门落盘的手动目录回 ``"draft"``（fail-closed 语义：draft
    不可 activate）。

    时序：manifest 写盘成功后才构造；构造失败不可能产生半成品回执。
    所有权：调用方只读消费,不得原地变更（frozen）。
    """

    assistant_id: str
    skill_id: str
    version: str
    digest: str
    """包内容摘要（``sha256:<hex>``；与 manifest ``digests`` 条目同源）。"""
    artifact_state: str
    installed_at: str
    """ISO-8601 UTC。"""
    revision_seq: int
    manifest_digest: str
    actor: str
    source: str = ""
    """安装源字面（``SkillSource.reference``）。"""
    install_path: str = ""
    """``{home}/skills/<skill_id>/`` 绝对路径。"""

    def __post_init__(self) -> None:
        if not self.assistant_id or not self.assistant_id.strip():
            raise ValueError("assistant_id 必为非空字符串")
        if not self.skill_id or not self.skill_id.strip():
            raise ValueError("skill_id 必为非空字符串")
        if not self.digest or not self.digest.strip():
            raise ValueError("digest 必为非空内容摘要")
        parse_artifact_state(self.artifact_state)  # 闭集校验;非法值抛异常
        if self.revision_seq < 0:
            raise ValueError(f"revision_seq 必为非负整数,得到 {self.revision_seq!r}")
        if not self.manifest_digest or not self.manifest_digest.strip():
            raise ValueError("manifest_digest 必为非空字符串")
        if not self.actor or not self.actor.strip():
            raise ValueError("actor 必为非空字符串")


@dataclass(frozen=True)
class SkillActivationReceipt:
    """``activate`` 的不可变回执（ADR-0187 §3 D8 四件套 + 激活标识）。

    activate 是 run 级事实,**不写** Home manifest、**不触发**
    ``revision_seq`` 变化；``revision_seq`` / ``manifest_digest`` 取事件
    时刻的 Home manifest 快照值。
    """

    assistant_id: str
    skill_id: str
    activation_id: str
    activated_at: str
    """ISO-8601 UTC。"""
    revision_seq: int
    manifest_digest: str
    actor: str
    artifact_state: str = ""
    """激活时刻 manifest 记录的包状态（``verified`` / ``active``）。"""

    def __post_init__(self) -> None:
        if not self.assistant_id or not self.assistant_id.strip():
            raise ValueError("assistant_id 必为非空字符串")
        if not self.skill_id or not self.skill_id.strip():
            raise ValueError("skill_id 必为非空字符串")
        if not self.activation_id or not self.activation_id.strip():
            raise ValueError("activation_id 必为非空字符串")
        if self.revision_seq < 0:
            raise ValueError(f"revision_seq 必为非负整数,得到 {self.revision_seq!r}")
        if not self.manifest_digest or not self.manifest_digest.strip():
            raise ValueError("manifest_digest 必为非空字符串")
        if not self.actor or not self.actor.strip():
            raise ValueError("actor 必为非空字符串")


# ── 失败语义异常 ─────────────────────────────────────────────────────


class SkillNotInstalled(LookupError):  # noqa: N818
    """``activate`` 找不到 ``{home}/skills/<skill_id>/`` 落盘包。"""


class SkillNotVerified(RuntimeError):  # noqa: N818
    """``activate`` 拒收：包未过 0067 三闸（artifact_state 非 VERIFIED/ACTIVE）。

    对应 ADR-0187 §3 D6「未验证包在 run 中不可被 `activate`」。
    """


# ── AssistantSkillOverlay Protocol ──────────────────────────────────


@runtime_checkable
class AssistantSkillOverlay(Protocol):
    """助理域 skill overlay —— install / list_installed / activate。

    实现约束（ADR-0187 §3 D4 / D6 + §6 删除条件）：

    1. 写路径 ⊆ ``{home}/skills/``；全局 ``~/.lca/skills/`` 只读不写
       （0048 机制复用,落点绑定本助理 Home）。
    2. install 必经 0067 三闸 + ``DRAFT → VERIFIED``；未验证不落盘、不发 EP。
    3. Catalog（``assistant.catalog``）拥有 Home / manifest digest 真值；
       本 Protocol 经 ``AssistantCatalog.get`` 拿 home_path 与 digest
       校验（fail-closed）,manifest skills 索引写入经
       ``lca.plugins.assistant._home_layout`` 既有函数完成。
    4. 单一类不得同时实现本 Protocol 与 ``AssistantCatalog`` /
       ``SkillAcquirer``（arch test 守住「无 God Catalog / 无平行进化协议」）。
    """

    async def install(
        self,
        assistant_id: str,
        source: SkillSource,
        *,
        actor: str = "system",
    ) -> SkillInstallReceipt:
        """安装 skill 到本助理 ``{home}/skills/`` 并发 ``assistant.skill.installed``。

        时序：``catalog.get`` digest 校验（fail-closed）⇒ 0048 拉取/校验进
        Home 内 staging ⇒ 0067 三闸 ⇒ DRAFT→VERIFIED ⇒ 落盘 +
        manifest ``digests``/``skills`` 更新 + ``revision_seq++`` ⇒ EP。

        失败语义：
        - ``assistant_id`` 不存在 / 配置面 digest 不匹配 ⇒ Catalog 异常透传；
        - 拉取 / 格式 / 三闸任一失败 ⇒ ``SkillImportError``（0048 异常族），
          不写 Home skills 索引、不发 EP；staging 清理。

        外部后果：``{home}/skills/<skill_id>/`` 出现 + manifest 修订 +
        一条 ``assistant.skill.installed`` Spine 事件。异步：网络拉取经
        ``SkillImporter.import_from_url``,调用方须 await。
        """
        ...

    def list_installed(self, assistant_id: str) -> tuple[SkillInstallReceipt, ...]:
        """扫 ``{home}/skills/`` 列已安装包（``skill_id`` 升序）。

        跨助理隔离：只读本助理 Home,不触达全局 store 或其他助理。
        落盘但无 manifest skills 索引记录的目录（手动放入）以
        ``artifact_state="draft"`` 回列 —— 可见但不可 activate。
        """
        ...

    def activate(
        self,
        assistant_id: str,
        skill_id: str,
        *,
        actor: str = "system",
    ) -> SkillActivationReceipt:
        """activate 已安装且已验证的 skill（fail-closed）+ 发 ``assistant.skill.activated``。

        失败语义：
        - ``assistant_id`` 不存在 / digest 不匹配 ⇒ Catalog 异常透传；
        - 包未落盘 ⇒ ``SkillNotInstalled``；
        - 落盘但 ``artifact_state`` 非 VERIFIED/ACTIVE ⇒ ``SkillNotVerified``。

        外部后果：仅一条 ``assistant.skill.activated`` Spine 事件；
        不写 Home（run 级事实,见 ``SkillActivationReceipt``）。
        """
        ...
