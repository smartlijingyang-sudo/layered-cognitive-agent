"""SOUL 文本校验与默认段合并（ADR-0242 D1/I-B2）。

原 ``catalog/plugin.py`` 的 SOUL 完整度校验、注入载荷拒绝、安全段回填、
角色卡目标提取与 USER.md 卫生规则，拆出后保持行为不变。
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.protocols.assistant.role_resolver import RoleCard
from lca.plugins.assistant.home._home_layout import (
    SOUL_SAFETY_SECTIONS,
    SoulValidationError,
    find_missing_soul_sections,
)

_SOUL_MIN_CHARS = 200
"""SOUL 完整度下限(去除全部空白后,中文按字符计;ADR-0242 D1)。"""

# 缺段错误附带的可照抄骨架:模型第一次重写常丢段,给模板可省一轮重试。
_SOUL_CORE_SKELETON = (
    "可直接照此骨架补全：\n"
    "## 🧠 身份\n<你是谁>\n"
    "## 🎭 性格\n<行事风格>\n"
    "## 🛠 能力\n<擅长与边界>\n"
    "## 🗣 语气\n<说话方式>"
)

# 零宽 / 方向控制字符：注入载荷常用载体（ClawHavoc、Zenity 实战记录）。
_ZERO_WIDTH_CHARS: tuple[str, ...] = (
    "\u200b",
    "\u200c",
    "\u200d",
    "\u200e",
    "\u200f",
    "\u2060",
    "\ufeff",
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
)

# 覆盖指令式 / 自我复制式载荷短语（中英混合，小写匹配）。
_SOUL_INJECTION_PATTERNS: tuple[str, ...] = (
    "忽略之前指令",
    "忽略上述指令",
    "无视之前",
    "无视上文",
    "忘记之前的指令",
    "ignore all previous",
    "ignore previous",
    "disregard all previous",
    "forget all previous",
    "override your instructions",
    "you are now",
    "act as if",
    "复制此指令",
    "把以上内容",
    "写入你的系统提示",
    "重复我上面的话",
)


def _reject_injected_soul(soul: str) -> None:
    """拒绝含注入载荷的 SOUL（fail-closed；Mind Viruses / PPA 威胁模型）。

    零宽字符命中即拒；指令覆盖 / 自我复制式短语命中即拒，错误消息给出命中模式，
    便于用户定位并清理。确定性错误不重试（C10）。
    """
    for char in _ZERO_WIDTH_CHARS:
        if char in soul:
            raise SoulValidationError(
                f"SOUL 含零宽/控制字符（U+{ord(char):04X}），疑似注入载荷，拒绝写入。"
                "请移除隐藏字符后重试。"
            )
    lowered = soul.lower()
    for pattern in _SOUL_INJECTION_PATTERNS:
        # 防御性规约：允许在安全段中声明拒绝该模式（如「拒绝『忽略之前指令』」）
        sanitized = (
            lowered.replace(f"拒绝「{pattern}」", "")
            .replace(f"拒绝『{pattern}』", "")
            .replace(f"拒绝“{pattern}”", "")
            .replace(f'拒绝"{pattern}"', "")
            .replace(f"拒绝'{pattern}'", "")
        )
        if pattern in sanitized:
            raise SoulValidationError(
                f"SOUL 命中指令覆盖/自我复制模式「{pattern}」，拒绝写入。"
                "SOUL.md 是人格配置不是指令来源，请移除该内容后重试。"
            )


def _validate_safety_sections_unchanged(current_soul: str, submitted_soul: str) -> None:
    """agent 修订 SOUL 时，安全段内容必须逐字节不变（红线只读化）。

    提交缺段会被 ``_merge_soul_defaults`` 补回，不算修改；提交显式给出与当前
    文件不同的安全段文案 → 拒绝。用户经 REST（actor=system）修改不受此限。
    """
    current_sections = _split_soul_sections(current_soul)
    submitted_sections = _split_soul_sections(submitted_soul)
    for marker in SOUL_SAFETY_SECTIONS:
        current = next((v for k, v in current_sections.items() if k.startswith(marker)), None)
        submitted = next((v for k, v in submitted_sections.items() if k.startswith(marker)), None)
        if current is not None and submitted is not None and current.strip() != submitted.strip():
            raise SoulValidationError(
                f"SOUL 安全段 {marker} 由平台保护，agent 不可修改。"
                "如需调整安全边界/记忆规则/错误处理/红线，请用户直接编辑 Home 文件。"
            )


def _validate_soul(soul: str) -> None:
    """SOUL 完整度校验(fail-closed;ADR-0242 I-B2)。

    校验项:
    1. 去除空白后长度 >= ``_SOUL_MIN_CHARS``;
    2. 必须包含四个核心语义段标记(身份/性格/能力/语气);
    3. 无注入载荷:零宽字符 / 覆盖指令式短语直接拒绝(I-B2 延伸,Mind Viruses 防护)。

    失败抛 :class:`SoulValidationError`,消息明确指出缺哪一段 / 长度不足 /
    命中的注入模式,便于向导继续对齐。安全边界/记忆规则/错误处理/红线由模板预置,
    不要求。
    """
    compact = "".join(soul.split())
    if len(compact) < _SOUL_MIN_CHARS:
        raise SoulValidationError(
            f"SOUL 完整度不足:去除空白后 {len(compact)} 字符,要求 >= {_SOUL_MIN_CHARS} 字符。"
            "请补充身份/性格/能力/语气的具体内容后再创建,不要用模板默认 SOUL 降级。"
        )
    _reject_injected_soul(soul)
    # 语义匹配（业界规范：normalize 后验语义）：接受 "## 身份"、"### 🧠身份"、
    # "## 🛠️ 能力"（emoji 变体选择符）等写法，不再要求字节级精确匹配。
    missing = find_missing_soul_sections(soul)
    if missing:
        raise SoulValidationError(
            "SOUL 缺少语义段: "
            + "、".join(f"「{name}」" for name in missing)
            + "。请补全这四个核心段(身份/性格/能力/语气)后重试;"
            "标题写法不限（含/不含 emoji、##/### 均可）;"
            "安全边界/记忆规则/错误处理/红线由模板预置,无需手写。\n" + _SOUL_CORE_SKELETON
        )


def _merge_soul_defaults(soul: str, template_soul: str) -> str:
    """把预置的安全段合并进用户 SOUL。

    用户向导只产出四个核心段;缺失的安全段按顺序从 ``template_soul``
    （创建路径 = 模板,revise 路径 = 当前文件或模板）提取并追加,
    保证最终 Home 的 SOUL 是完整的八段结构。
    """
    if all(marker in soul for marker in SOUL_SAFETY_SECTIONS):
        return soul
    sections = _split_soul_sections(template_soul)
    defaults: list[str] = []
    for marker in SOUL_SAFETY_SECTIONS:
        if marker in soul:
            continue
        # 模板标题可能是 ``## 🚫 红线（凌驾一切）`` 这类扩展形式,按前缀匹配。
        section = next((v for k, v in sections.items() if k.startswith(marker)), None)
        if section is not None:
            defaults.append(section)
    if not defaults:
        return soul
    return soul.rstrip() + "\n\n" + "\n\n".join(defaults) + "\n"


def _split_soul_sections(soul: str) -> dict[str, str]:
    """按 ``## `` 标题把 SOUL 文本切成 ``{标题: 完整节块}``。"""
    sections: dict[str, str] = {}
    current_marker: str | None = None
    current: list[str] = []
    for line in soul.splitlines():
        if line.startswith("## "):
            if current_marker is not None:
                sections[current_marker] = "\n".join(current).strip()
            current_marker = line.strip()
            current = [line]
        elif current_marker is not None:
            current.append(line)
    if current_marker is not None:
        sections[current_marker] = "\n".join(current).strip()
    return sections


def _mission_goal_names(backstory: str, limit: int = 3) -> list[str]:
    """从角色卡 backstory 的「核心使命」段提取 ``###`` 标题作为目标名(ADR-0242 D2)。"""
    lines = backstory.splitlines()
    in_mission = False
    goals: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_mission = "核心使命" in stripped
            continue
        if in_mission and stripped.startswith("### "):
            name = stripped[4:].strip()
            if name and len(goals) < limit:
                goals.append(name)
    return goals


def _goals_yaml_from_role_card(card: RoleCard) -> str:
    """把角色卡核心使命的前三个目标写成非空 goals.yaml(ADR-0242 D2)。

    角色卡没有「核心使命」段时,用角色标题兜底保证 goals.yaml 非空。
    """
    goal_names = _mission_goal_names(card.backstory)
    if not goal_names:
        goal_names = [f"{card.title}核心职责"]
    lines = ["goals:"]
    for name in goal_names:
        lines.append(f"  - name: {name}")
        lines.append(f"    description: 来自角色卡「核心使命」的目标,围绕「{name}」持续交付。")
        lines.append("    success_criteria: 完成该目标下的关键交付物并得到用户认可。")
    lines.append("notes: |")
    lines.append("  目标提取自角色卡「核心使命」段;可经 revise_profile 调整。")
    return "\n".join(lines) + "\n"


_DEFAULT_USER_MD = """# USER

助理服务的对象画像。请在向导中或首次对话中补充以下内容:

- **称呼**:用户希望被怎么称呼?
- **服务对象**:用户的主要身份(如:开发者、产品经理、学生)?
- **偏好**:回复风格、常用工具、禁忌话题?
- **上下文**:用户当前项目 / 场景的关键背景?
"""


def _ensure_non_empty_user_md(home: Path) -> None:
    """Home 卫生:USER.md 不允许为空(ADR-0242 D2)。

    模板已提供可填充骨架;本守卫只在文件缺失或空白时写入默认骨架,
    保证向导创建 / 裸创建的 Home 都不含空 USER.md。
    """
    user_md = home / "USER.md"
    if not user_md.is_file() or not user_md.read_text(encoding="utf-8").strip():
        user_md.write_text(_DEFAULT_USER_MD, encoding="utf-8")
