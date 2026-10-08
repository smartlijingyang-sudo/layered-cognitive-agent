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

from lca.contracts.atoms.artifact.state import parse_artifact_state

__all__ = [
    "AssistantSkillOverlay",
    "SkillActivationReceipt",
    "SkillInstallReceipt",
    "SkillNotInstalledError",
    "SkillNotVerifiedError",
    "SkillRelinkReport",
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
        elif not self.local_path.startswith("/"):
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


@dataclass(frozen=True)
class SkillRelinkReport:
    """``relink_global_skills`` 的不可变报告（ADR-0243 D1「显式 re-link 才升级」）。

    四个 skill_id 元组是 Home manifest ``skills`` 索引的**互斥穷尽**分类：索引里
    每个条目恰好落进一个。``skills/`` 下无索引记录的目录不在报告内（不属全局链接
    治理面，re-link 不动它）。``skipped_missing_global`` 同时覆盖「全局包不存在」
    与「全局包已退役」——两者都不构成删除授权。

    ``revision_seq`` / ``manifest_digest`` 是调用结束时 Home manifest 的值：
    ``relinked`` 非空 ⇒ 整批只 ``revision_seq++`` 一次后的新值；``relinked``
    为空 ⇒ 原值（一个字节都不写盘）。

    时序：manifest 写盘（若发生）成功后才构造;构造失败不可能产生半成品报告。
    所有权：调用方只读消费,不得原地变更（frozen）。
    """

    assistant_id: str
    revision_seq: int
    manifest_digest: str
    relinked: tuple[str, ...] = ()
    """硬链接已换成全局当前版本的技能（skill_id 升序）。"""
    already_current: tuple[str, ...] = ()
    """``global_link`` 且包摘要与全局一致 ⇒ 未触盘、未进修订。"""
    skipped_local: tuple[str, ...] = ()
    """索引里 ``source`` 非 ``global_link`` 的条目（助理自有副本,含 install 源字面）。"""
    skipped_missing_global: tuple[str, ...] = ()
    """全局包缺失或已退役 ⇒ Home 条目与索引原样保留（版本固定;删除走 ``remove``）。"""

    def __post_init__(self) -> None:
        if not self.assistant_id or not self.assistant_id.strip():
            raise ValueError("assistant_id 必为非空字符串")
        if self.revision_seq < 0:
            raise ValueError(f"revision_seq 必为非负整数,得到 {self.revision_seq!r}")


# ── 失败语义异常 ─────────────────────────────────────────────────────


class SkillNotInstalledError(LookupError):
    """``activate`` 找不到 ``{home}/skills/<skill_id>/`` 落盘包。"""


class SkillNotVerifiedError(RuntimeError):
    """``activate`` 拒收：包未过 0067 三闸（artifact_state 非 VERIFIED/ACTIVE）。

    对应 ADR-0187 §3 D6「未验证包在 run 中不可被 `activate`」。
    """


# ── AssistantSkillOverlay Protocol ──────────────────────────────────


@runtime_checkable
class AssistantSkillOverlay(Protocol):
    """助理域 skill overlay —— install / list_installed / activate。

    实现约束（ADR-0187 §3 D4 / D6 + §6 删除条件）：

    1. 写路径 ⊆ ``{home}/skills/``；全局 ``~/.lca/skills/`` 只读不写
       （0048 机制复用,落点绑定本助理 Home）。``relink_global_skills`` 是唯一
       读全局库的动作:读内容源当前状态,不写全局库、不触发全局库自身刷新。
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
        - 包未落盘 ⇒ ``SkillNotInstalledError``；
        - 落盘但 ``artifact_state`` 非 VERIFIED/ACTIVE ⇒ ``SkillNotVerifiedError``。

        外部后果：仅一条 ``assistant.skill.activated`` Spine 事件；
        不写 Home（run 级事实,见 ``SkillActivationReceipt``）。
        """
        ...

    async def remove(
        self,
        assistant_id: str,
        skill_id: str,
        *,
        actor: str = "system",
    ) -> None:
        """删除本助理已安装的 skill（ADR-0242 D6）。

        时序：``catalog.get`` digest 校验（fail-closed）⇒ 删除
        ``{home}/skills/<skill_id>/`` ⇒ manifest 重算 + ``revision_seq++``
        ⇒ 发 ``assistant.profile.revised`` EP（配置变更统一走该 EP）。

        失败语义：
        - ``assistant_id`` 不存在 / digest 不匹配 ⇒ Catalog 异常透传；
        - 包未落盘 ⇒ ``SkillNotInstalledError``（不删盘、不发 EP）。

        外部后果：``{home}/skills/<skill_id>/`` 消失 + manifest 修订 +
        一条 ``assistant.profile.revised`` Spine 事件。
        """
        ...

    async def edit(
        self,
        assistant_id: str,
        skill_id: str,
        skill_md: str,
        *,
        actor: str = "system",
    ) -> SkillInstallReceipt:
        """编辑本助理已安装的 skill（ADR-0243 PR-3，COW）。

        时序：``catalog.get`` digest 校验（fail-closed）⇒ 若包来源为
        ``global_link`` 先断链复制为 ``local`` ⇒ staging 内校验新
        SKILL.md（0048 结构上限 + 0067 三闸）⇒ 覆盖落盘
        ``{home}/skills/<skill_id>/`` ⇒ manifest 重算 + ``revision_seq++``
        ⇒ 发 ``assistant.profile.revised`` EP。

        失败语义：
        - ``assistant_id`` 不存在 / digest 不匹配 ⇒ Catalog 异常透传；
        - 包未落盘 ⇒ ``SkillNotInstalledError``（不写盘、不发 EP）；
        - 新 SKILL.md 校验失败 ⇒ ``SkillImportError``（不写盘、不发 EP）。

        外部后果：``{home}/skills/<skill_id>/`` 内容更新 + manifest 修订 +
        一条 ``assistant.profile.revised`` Spine 事件。
        """
        ...

    def relink_global_skills(
        self,
        assistant_id: str,
        *,
        actor: str = "system",
    ) -> SkillRelinkReport:
        """把 ``global_link`` 技能重链到全局库当前版本（ADR-0243 D1 显式升级路径）。

        时序：``catalog.get`` 解析 Home（配置面 digest 不一致时按 ADR-0187 §3 D2
        自愈 reimport 后继续,读路径不阻断）⇒ 取 Home manifest
        ``skills`` 索引里 ``source == "global_link"`` 的条目 ⇒ 逐个按包内容摘要
        与全局包比对 ⇒ 需升级者先在 ``{home}/skills/.staging/`` 内硬链接成包并过
        0067 三闸 ⇒ 全部成包后才落盘 ⇒ **整批一次** manifest 修订
        （``revision_seq++`` 一次 + 一份 ``revisions/`` 快照）⇒ 每个重链技能一条
        ``assistant.skill.installed`` EP。

        失败语义：
        - ``assistant_id`` 不存在 ⇒ Catalog 异常透传；
        - 全局包缺失 / 已退役 ⇒ 进 ``skipped_missing_global``，Home 落盘与索引
          条目**原样保留**（版本固定;删除授权只在 ``remove``）；
        - 索引里 ``source`` 非 ``global_link`` 的条目一律不动，进 ``skipped_local``；
        - 全局包过不了 0067 三闸 ⇒ ``SkillImportError`` 透传，此时尚未落盘、
          未写 manifest、未发 EP。

        外部后果：``{home}/skills/<skill_id>/`` 内容换成全局当前版本的硬链接；
        仅当 ``relinked`` 非空时有一次 manifest 修订与逐技能一条
        ``assistant.skill.installed``。同步:只读全局库 + 只写本助理 Home，无网络。
        """
        ...
