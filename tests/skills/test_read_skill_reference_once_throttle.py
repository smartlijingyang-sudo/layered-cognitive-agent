"""ReadSkillReferenceThrottle 节流测试(ADR-0214 §7.3)。

5 fixture:
1. 同一 (skill_id, path) 失败 1 次 → 不节流
2. 失败 2 次 → 触发节流, 抛 SkillContractError
3. 失败 2 次后成功 1 次 → 节流窗口滑动, 重置
4. 不同 (skill_id, path) 独立计数
5. 窗口外老失败不计
"""

from __future__ import annotations

import unittest

from lca.contracts.protocols.memory.operational_skills import SkillContractError
from lca.infrastructure.tools.skills.read.reference_tool import ReadSkillReferenceThrottle


class TestReadSkillReferenceThrottle(unittest.TestCase):
    def test_one_failure_does_not_throttle(self) -> None:
        """同一 (skill_id, path) 失败 1 次 → 不抛。"""
        t = ReadSkillReferenceThrottle()
        # 第一次失败不应抛
        t.check_and_record("s1", "p1", success=False)

    def test_two_failures_trigger_throttle(self) -> None:
        """失败 ≥ 2 → 抛 SkillContractError(ADR-0214 §7.3)。"""
        t = ReadSkillReferenceThrottle()
        t.check_and_record("s1", "p1", success=False)
        with self.assertRaises(SkillContractError) as ctx:
            t.check_and_record("s1", "p1", success=False)
        msg = str(ctx.exception)
        self.assertIn("s1", msg)
        self.assertIn("p1", msg)
        self.assertIn("节流", msg)

    def test_window_resets_with_success(self) -> None:
        """失败 2 次触发后, 重置并用足够成功填充窗口, 后续单次失败不触发。

        模拟场景: 进程级 throttle 触发了, 工具层捕获异常后做了一次
        重新尝试,本次成功把窗口"挤"过去,模型后续再尝试读同一路径
        不会被立刻熔断。
        """
        t = ReadSkillReferenceThrottle(window=5, threshold=2)
        # 触发一次
        t.check_and_record("s1", "p1", success=False)
        with self.assertRaises(SkillContractError):
            t.check_and_record("s1", "p1", success=False)
        # 显式重置(recovery hook, 由调用方在熔断后决策是否调用)
        t.reset("s1", "p1")
        # 1 次失败 + 5 次成功(填满 maxlen=5) + 1 次失败
        t.check_and_record("s1", "p1", success=False)
        for _ in range(5):
            t.check_and_record("s1", "p1", success=True)
        # 此时 window=[F,F,F,F,F], 1 fail→[F,F,F,F,F,T], fails=1, 不抛
        t.check_and_record("s1", "p1", success=False)

    def test_independent_counts_per_key(self) -> None:
        """不同 (skill_id, path) 独立计数。"""
        t = ReadSkillReferenceThrottle()
        # s1/p1 触发节流
        t.check_and_record("s1", "p1", success=False)
        with self.assertRaises(SkillContractError):
            t.check_and_record("s1", "p1", success=False)
        # s1/p2 不应受影响
        t.check_and_record("s1", "p2", success=False)
        # s2/p1 不应受影响
        t.check_and_record("s2", "p1", success=False)

    def test_old_failures_outside_window_dont_count(self) -> None:
        """超过 window 大小的老失败被滑出窗口,不再计数。"""
        t = ReadSkillReferenceThrottle(window=5, threshold=2)
        # 5 次成功把首个失败滑出窗口
        t.check_and_record("s1", "p1", success=False)  # → history=[T]
        # 现在填 5 次成功(maxlen=5)
        for _ in range(5):
            t.check_and_record("s1", "p1", success=True)  # → history=[T,F,F,F,F]
        # 此时 failures 在窗口里,但我们先记录一次 reset 再观察
        t.reset("s1", "p1")
        # 1 次失败不应触发
        t.check_and_record("s1", "p1", success=False)
        # 紧接着 5 次成功,再 1 次失败 → 同样只 1 fail, 不触发
        for _ in range(5):
            t.check_and_record("s1", "p1", success=True)
        t.check_and_record("s1", "p1", success=False)


class TestReadSkillReferenceThrottleResetSemantics(unittest.TestCase):
    """reset() 行为 — recovery / 测试 fixture 用。"""

    def test_reset_all(self) -> None:
        t = ReadSkillReferenceThrottle()
        t.check_and_record("s1", "p1", success=False)
        t.check_and_record("s2", "p2", success=False)
        t.reset()  # 全部清空
        # 不应再受影响
        t.check_and_record("s1", "p1", success=False)

    def test_reset_specific_key(self) -> None:
        t = ReadSkillReferenceThrottle()
        t.check_and_record("s1", "p1", success=False)
        t.reset(skill_id="s1")  # 清空所有 s1 的条目
        # s1/p1 不再受影响
        t.check_and_record("s1", "p1", success=False)


if __name__ == "__main__":
    unittest.main()
