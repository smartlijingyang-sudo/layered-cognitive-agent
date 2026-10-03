"""ADR-0276 T8 / ADR-0257 §7：子 agent 继承的同机/peer 区分契约钉。

0255 §6 T8 要求"子 agent 首 turn 即拥有与父相同的身份与记忆注入"；
ADR-0257 §7（李超 132f381a8 裁决）把"相同"拆成两种形态：
- 同机 subagent：全量 standing 快照（现状 ``assemble_standing``，已有
  ``tests/runtime/test_adr0255_muse_runtime_conformance.py::test_t8_...`` 覆盖）。
- peer（跨机/跨组织，如 peter）：脱敏信封 ``standing_redacted``，PII 不出境。

实证：2026-10-03 全仓 grep，``standing_redacted`` 在 ``lca/`` 与 ``tests/``
零符号——决议已裁决、实现零落地。test_t8 只断言同机快照 9 文件装配，
T8 行的"未覆盖同机/peer 区分（0257 §7）"正是 0276 映射表点名的缺口。

本文件 tests lane 定义契约 seam（quality lane 实现时遵循；开放设计点已标注）：
- ``lca.infrastructure.memory.contextfiles.domain.peer_standing.pack_peer_standing(
      files, *, budget_chars, order=None) -> str``
  - ``files``：同 ``assemble_standing`` 的 ``(name, body)`` 序列。
  - ``budget_chars`` / ``order`` 语义同 ``assemble_standing``。
  - 返回 peer 版 standing 文本：样本 PII 字串不得出境（mask/删除/哈希由
    quality 定，本测试只断言样本 PII 不在输出中——算法可换，契约不变）。
  - 输出必须带 provenance 标记 ``standing_redacted``（0258 C2 血统要求在事件
    descriptor 落点之前，先以文本标记钉住可观测性）。
  - 结构保留：``packaged_layout().standing_files`` 的注入骨架仍在
    （``<!-- INJECTED FILE: <name> -->`` 槽位不丢，只脱敏内容）。
- 开放设计点：脱敏算法（mask vs 删除 vs 占位）、PII 类别清单落点（是否复用
  0253/0266 凭证红线清单）、peer 判定由谁传入（dispatch 参数 vs envelope
  字段）由 quality/arch 定；本测试只钉"同输入→peer 输出 PII 缺席且与同机
  输出不同"。
"""

from __future__ import annotations

try:
    from lca.infrastructure.memory.contextfiles.domain.peer_standing import (
        pack_peer_standing,
    )
except ImportError:  # ADR-0257 §7 已裁决、源码侧零落地：peer 脱敏包缺席
    pack_peer_standing = None  # type: ignore[assignment]

from lca.infrastructure.memory.contextfiles.domain.layout import packaged_layout
from lca.infrastructure.memory.contextfiles.domain.standing import assemble_standing


def _require(name: str, sym):
    assert sym is not None, f"ADR-0257 §7 未落地：{name} 缺席（预期红契约钉）"
    return sym


# 样本 PII：只用于断言"不出境"，非真实用户数据。
_SAMPLE_PII = (
    "13800001111",
    "user@example.com",
    "长沙市雨花区测试路 1 号",
)

_SAMPLE_FILES = [
    ("SOUL.md", "# Soul\n联系电话 13800001111，邮箱 user@example.com。"),
    ("IDENTITY.md", "# Identity\n代号 Athena。"),
    ("USER.md", "# User\n住址：长沙市雨花区测试路 1 号。"),
    ("MEMORY.md", "# Memory\n公开偏好：喜欢深夜写代码。"),
    ("AGENTS.md", "# Agents\n协作铁律 v2。"),
    ("TOOLS.md", "# Tools\n本地 notes。"),
    ("memory/people/INDEX.md", "# People\n公开名单。"),
    ("memory/groups/INDEX.md", "# Groups\n公开群组。"),
    ("dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md", "# Alignment\n公开综述。"),
]


def _peer(files=_SAMPLE_FILES, budget_chars=8000):
    pack = _require(
        "lca.infrastructure.memory.contextfiles.domain.peer_standing.pack_peer_standing",
        pack_peer_standing,
    )
    return pack(files, budget_chars=budget_chars)


class TestPeerStandingRedaction:
    def test_seam_present(self):
        """peer 脱敏包 seam 存在（ADR-0257 §7 落地的第一步）。"""
        _require(
            "lca.infrastructure.memory.contextfiles.domain.peer_standing.pack_peer_standing",
            pack_peer_standing,
        )

    def test_peer_output_drops_sample_pii(self):
        """peer 输出不得含样本 PII 原文——脱敏是真行为，不是换了个函数名。"""
        out = _peer()
        for pii in _SAMPLE_PII:
            assert pii not in out, f"PII 出境：{pii!r} 出现在 peer standing 输出中"

    def test_peer_output_carries_redaction_marker(self):
        """peer 输出带 standing_redacted 血统标记（0258 C2 可观测性先行）。"""
        out = _peer()
        assert "standing_redacted" in out

    def test_peer_keeps_standing_skeleton(self):
        """脱敏只动内容不动骨架：9 文件注入槽位全部保留。"""
        out = _peer()
        layout = packaged_layout()
        for name in layout.standing_files:
            assert f"<!-- INJECTED FILE: {name} -->" in out, f"骨架丢失：{name}"

    def test_peer_differs_from_same_machine_snapshot(self):
        """同输入、同预算下 peer 输出与同机全量快照必须不同（"区分"二字钉死）。"""
        out = _peer()
        full = assemble_standing(_SAMPLE_FILES, budget_chars=8000)
        assert out != full


class TestSameMachineBaselineUnchanged:
    def test_same_machine_keeps_pii_verbatim(self):
        """同机快照保持全量（含 PII 原文）——peer 脱敏不得反向污染同机路径。

        本用例当前为绿：它是"区分"的基准线；若将来同机快照也被脱敏，
        说明 0257 §7 的两形态区分被实现抹平，本用例会如实变红。
        """
        full = assemble_standing(_SAMPLE_FILES, budget_chars=8000)
        assert "13800001111" in full
        assert "user@example.com" in full
