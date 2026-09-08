"""PR-E.1 — `lab.*` capability 闭集测试守护（ADR-0209 §1.4 / §3 I-8）.

闭集权威来源：[`docs/specs/capability-closed-set.md`](../../docs/specs/capability-closed-set.md) §1.4
的 set 字面量（``ast.literal_eval`` 原生支持 set 字面量）；测试再 ``frozenset(...)``
包一层做集合语义校验。

四项断言（与 spec §4 一一对应）：
  1. 闭集字面量与 ADR-0209 §1.4 + design spec §C 列出的 ``lab.*`` 期望完全一致；
  2. ``lca/plugins/lab/**/*.py`` 中 ``provides=[...]`` 含 ``lab.`` 的 key 必须落在闭集内；
  3. ``lca/plugins/lab/**/*.py`` 中 ``requires=[...]`` 含 ``lab.`` 的 key 必须落在闭集内；
  4. ``bundles/*.yaml`` / ``profiles/*.yaml`` 中声明的 ``lab.`` capability 必须落在闭集内。

失败语义：
  - 解析失败 / 期望不一致 → ``AssertionError``；
  - plugin / YAML 提供方或消费方尚未声明任何 ``lab.`` key → ``pytest.skip``；
    PR-A/B/C/D 推进过程中一旦新增 plugin 文件 / YAML 声明即自动校验。
  - 已声明 ``lab.`` key 但不在闭集 → ``AssertionError``（**fail-loud**：测试
    即是 ADR-0209 §3 I-8 的「闭集看门狗」）。

不修改生产代码：闭集新增由 ADR + spec §1.4 同步推进，测试只是看门狗。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "specs" / "capability-closed-set.md"
LAB_PLUGIN_DIR = ROOT / "lca" / "plugins" / "lab"
BUNDLES_DIR = ROOT / "bundles"
PROFILES_DIR = ROOT / "profiles"

# 期望闭集 = ADR-0209 §1.4 + design spec §C 中列出的 lab.* key 全集；
# 与 spec §1.4 frozenset 字面量必须完全一致。
EXPECTED_LAB_KEYS: frozenset[str] = frozenset(
    {
        # §1.1 装配面 provider provides
        "lab.session",
        "lab.plan_ref",
        "lab.body",
        "lab.tool_registry",
        "lab.safe_executor",
        "lab.transport",
        # §1.2 工兵产出
        "lab.act.shape.out:intent",
        "lab.act.authorize.out:authorized",
        "lab.act.execute.out:receipt",
        "lab.act.observe.out:observation",
        "lab.perceive.sense.out:sensor_items",
        "lab.perceive.resolve.out:sensors",
        "lab.perceive.policy.out:policy",
        "lab.perceive.memory.out:memory_items",
        "lab.perceive.trim.out:trimmed",
        "lab.perceive.commit.out:committed",
        "lab.think.expose.out:messages",
        "lab.think.expose.out:tools",
        "lab.think.reason.out:response",
        "lab.think.classify.out:decision",
        "lab.think.guard.out:decision",
        "lab.think.guard.out:think_signal",
        "lab.reflect.critique.out:critique",
        "lab.reflect.extract.out:lesson",
        "lab.reflect.join.out:reflection",
        "lab.remember.admit.out:fact",
        "lab.remember.commit.out:remembered",
        "lab.remember.fold_history.out:history",
        "lab.remember.snapshot.out:snapshot",
        # §1.3 plugin hook 入口
        "lab.hooks.compiletime.before_compile",
        "lab.hooks.compiletime.after_compile",
        "lab.hooks.runtime.node_start",
        "lab.hooks.runtime.node_end",
        "lab.hooks.runtime.after_node_execute",
        "lab.hooks.runtime.edge_fire",
        "lab.hooks.runtime.subgraph_enter",
        "lab.hooks.runtime.subgraph_exit",
        "lab.hooks.semantic.on_decision",
        "lab.hooks.semantic.on_observation",
        "lab.hooks.semantic.on_reflection",
        "lab.hooks.semantic.on_event",
    }
)

# 提取 ``provides=[...]`` / ``requires=[...]`` 中字符串字面量（支持多行 + 嵌套括号）。
_LIST_OF_STRINGS_RE = re.compile(
    r"""
    (?P<kw>provides|requires)         # 关键字
    \s*=\s*                           # 等号
    \[                                # 列表开
    (?P<body>(?:[^][]|\[[^][]*\])*)   # 列表体（不含外层 [ ]）
    \]                                # 列表闭
    """,
    re.VERBOSE | re.DOTALL,
)
# 单个字符串字面量（"..." 或 '...'）。
_STRING_LITERAL_RE = re.compile(r"""(?P<q>['"])(?P<key>lab\.[A-Za-z0-9_.:]+)(?P=q)""")
# YAML 中的 lab.* capability key：要求 ``lab.`` 之前不是字母 / 数字 /
# 下划线（避免误匹配 ``agent_lab.runtime.runner`` 中的子串 ``lab.runtime.runner``）。
# capability key 的合法字面量形式：`lab.<area>.<name>` 或
# `lab.<area>.<name>.out:<port>`，允许引号包围。
_YAML_LAB_KEY_RE = re.compile(
    r"""(?:^|(?<=[\s\[\(,:=\-"']))(?P<key>lab\.[A-Za-z0-9_.:]+)(?=[\s\],):=]|$)"""
)


def _parse_spec_closed_set() -> frozenset[str]:
    """从 spec §1.4 ```text``` 字面量解析闭集。

    spec §1.4 写 ``{...}``（set 字面量，``ast.literal_eval`` 原生支持）；
    本函数再 ``frozenset(...)`` 包一层做集合语义校验。

    §1.4 是「总闭集」：在所有 ``{...}`` 字面量中**元素最多**。spec §1.1–§1.3
    是分段子集，元素数更少；以大小最大者为目标块。

    失败抛 ``pytest.skip``：spec 暂未落档（极早期），其余测试同步 skip。
    """
    if not SPEC.exists():
        pytest.skip(f"spec file not found: {SPEC}")
    text = SPEC.read_text(encoding="utf-8")
    fenced = re.findall(r"```text\n(.*?)```", text, flags=re.DOTALL)
    if not fenced:
        pytest.skip("no ```text``` fenced block in spec")
    parsed: list[set[str]] = []
    for block in fenced:
        stripped = block.strip()
        if not (stripped.startswith("{") and stripped.endswith("}")):
            continue
        value = _safe_literal_eval(stripped)
        if isinstance(value, set):
            parsed.append(value)
    if not parsed:
        pytest.skip("no set 字面量 {...} block in spec §1.4")
    # §1.4 是最大者；其余 §1.1–§1.3 是小子集。
    target = max(parsed, key=len)
    if not isinstance(target, set):
        raise AssertionError(f"spec §1.4 字面量必须解析为 set，实得 {type(target).__name__}")
    return frozenset(target)


def _safe_literal_eval(source: str) -> object:
    """``ast.literal_eval`` 的薄包装，失败时给出位置提示。"""
    try:
        return ast.literal_eval(source)
    except (SyntaxError, ValueError) as exc:
        raise AssertionError(f"spec §1.4 set 字面量解析失败：{exc}") from exc


def _scan_keys_in_python(path: Path) -> dict[str, list[int]]:
    """在单个 .py 文件中提取 ``provides=[...]`` / ``requires=[...]`` 中的 ``lab.`` 字符串 key。

    返回 ``{key: [行号, ...]}``；空 dict = 该文件未声明任何 ``lab.`` key。
    """
    if not path.exists() or path.suffix != ".py":
        return {}
    text = path.read_text(encoding="utf-8")
    found: dict[str, list[int]] = {}
    for match in _LIST_OF_STRINGS_RE.finditer(text):
        body = match.group("body")
        # 把 body 内的绝对偏移换算回 text 内的绝对偏移
        body_start_in_text = match.start("body")
        for str_match in _STRING_LITERAL_RE.finditer(body):
            key = str_match.group("key")
            abs_pos = body_start_in_text + str_match.start()
            line_no = text[:abs_pos].count("\n") + 1
            found.setdefault(key, []).append(line_no)
    return found


def _scan_keys_in_yaml(path: Path) -> dict[str, list[int]]:
    """在单个 YAML 文件中粗扫 ``lab.`` capability key 声明。

    精确语义（requires vs provides）由调用方按 YAML 结构判断；本测试只
    取「任何字符串字面量形如 ``lab.<x>``」的 key 并报告行号，让审计员目
    视决定是否误用。
    """
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    found: dict[str, list[int]] = {}
    for match in _YAML_LAB_KEY_RE.finditer(text):
        key = match.group("key")
        line_no = text[: match.start()].count("\n") + 1
        found.setdefault(key, []).append(line_no)
    return found


# ── §1 闭集字面量与期望闭集一致 ──────────────────────────────────────


def test_lab_capability_keys_are_closed() -> None:
    """``lab.*`` capability keys are exactly those in capability-closed-set.md.

    解析 spec §1.4 frozenset 字面量，与本测试的 ``EXPECTED_LAB_KEYS`` 硬编码
    期望比对；二者不一致 = spec 与 ADR-0209 §1.4 漂移，**必改 spec + ADR**。
    """
    spec_keys = _parse_spec_closed_set()
    assert spec_keys == EXPECTED_LAB_KEYS, (
        f"spec §1.4 frozenset 与期望闭集漂移：\n"
        f"  缺（spec 没有，期望有）：{sorted(EXPECTED_LAB_KEYS - spec_keys)}\n"
        f"  多（spec 有，期望没有）：{sorted(spec_keys - EXPECTED_LAB_KEYS)}"
    )


# ── §2 plugin 文件 provides=[...] 含 lab.* ────────────────────────────


def test_no_undeclared_lab_capability_in_provides() -> None:
    """每个 ``provides=[...]`` 含 ``lab.`` 的 plugin 文件，键必须在闭集内。

    当前 `lca/plugins/lab/` 仅含 `internal/hooks.py`（私有 helper，PR-A.2
    落地），未声明 ``provides=[...]``；扫描结果为空集合即通过。后续 PR-A/B/C/D
    新增 plugin 文件后，本测试自动生效校验。
    """
    if not LAB_PLUGIN_DIR.exists():
        pytest.skip(f"lab plugin 目录尚未建立（PR-A.2 仅落 internal/hooks.py）: {LAB_PLUGIN_DIR}")
    closed = _parse_spec_closed_set()
    violations: list[str] = []
    found_any = False
    for py in sorted(LAB_PLUGIN_DIR.rglob("*.py")):
        if py.name == "__init__.py":
            continue
        keys_with_lines = _scan_keys_in_python(py)
        if not keys_with_lines:
            continue
        found_any = True
        for key, lines in keys_with_lines.items():
            if key not in closed:
                rel = py.relative_to(ROOT)
                violations.append(f"  {rel} 行 {lines}：provides 声明 {key!r} 不在闭集")
    if not found_any:
        pytest.skip("`lca/plugins/lab/` 下尚未存在声明 provides 的 plugin 文件（PR-A/B/C/D 推进）")
    assert not violations, "未登记的 `lab.*` capability 出现在 plugin provides：\n" + "\n".join(
        violations
    )


# ── §3 plugin 文件 requires=[...] 含 lab.* ────────────────────────────


def test_no_undeclared_lab_capability_in_requires() -> None:
    """每个 ``requires=[...]`` 含 ``lab.`` 的 plugin 文件，键必须在闭集内。

    同 §2：当前 lab plugin 目录无 requires 声明 → skip；PR-A/B/C/D 之后即
    自动校验。
    """
    if not LAB_PLUGIN_DIR.exists():
        pytest.skip(f"lab plugin 目录尚未建立: {LAB_PLUGIN_DIR}")
    closed = _parse_spec_closed_set()
    violations: list[str] = []
    found_any = False
    for py in sorted(LAB_PLUGIN_DIR.rglob("*.py")):
        if py.name == "__init__.py":
            continue
        text = py.read_text(encoding="utf-8")
        # requires 关键字扫描
        for kw_match in re.finditer(r"requires\s*=\s*\[", text):
            start = kw_match.end()
            depth = 1
            i = start
            while i < len(text) and depth:
                c = text[i]
                if c == "[":
                    depth += 1
                elif c == "]":
                    depth -= 1
                i += 1
            body = text[start : i - 1]
            for str_match in _STRING_LITERAL_RE.finditer(body):
                key = str_match.group("key")
                abs_pos = start + str_match.start()
                line_no = text[:abs_pos].count("\n") + 1
                if key not in closed:
                    rel = py.relative_to(ROOT)
                    violations.append(f"  {rel} 行 {line_no}：requires 声明 {key!r} 不在闭集")
                found_any = True
    if not found_any:
        pytest.skip("`lca/plugins/lab/` 下尚未存在声明 requires 的 plugin 文件（PR-A/B/C/D 推进）")
    assert not violations, "未登记的 `lab.*` capability 出现在 plugin requires：\n" + "\n".join(
        violations
    )


# ── §4 YAML 中 lab.* capability 声明 ──────────────────────────────────


def test_no_undeclared_lab_capability_in_yaml() -> None:
    """每个 Profile / Bundle YAML 含 ``lab.`` capability 声明的，键必须在闭集内。

    当前仅 ``profiles/agent-lab-infoedge.yaml`` 与 ``bundles/agent-lab-infoedge.yaml``
    的注释含 ``agent_lab.runtime.runner`` 字样（不属于 ``lab.`` capability 闭集词
    形）；本测试扫描不到任何 ``lab.<x>`` 字面量时即通过。
    """
    closed = _parse_spec_closed_set()
    violations: list[str] = []
    scanned: list[tuple[Path, dict[str, list[int]]]] = []
    for search_dir in (BUNDLES_DIR, PROFILES_DIR):
        if not search_dir.exists():
            continue
        for yml in sorted(search_dir.rglob("*.yaml")):
            keys_with_lines = _scan_keys_in_yaml(yml)
            if keys_with_lines:
                scanned.append((yml, keys_with_lines))
    for yml, keys_with_lines in scanned:
        for key, lines in keys_with_lines.items():
            if key not in closed:
                rel = yml.relative_to(ROOT)
                violations.append(f"  {rel} 行 {lines}：YAML 声明 {key!r} 不在闭集")
    if not scanned:
        pytest.skip("bundles/ profiles/ 下尚未声明任何 `lab.*` capability（PR-B/C 推进）")
    assert not violations, (
        "未登记的 `lab.*` capability 出现在 Profile / Bundle YAML：\n" + "\n".join(violations)
    )
