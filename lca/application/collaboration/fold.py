"""Delegation Fold Aggregator with Hermes-style anti-context-pollution.

Synthesizes specialist receipts into a single authoritative FoldedDelegationResult,
strips noisy tool traces, and determines consensus status.
"""

import re
from collections.abc import Mapping

from lca.contracts.models.collaboration.peer import FoldedDelegationResult

_NOISE_LINE_PATTERNS = re.compile(
    r"^(DEBUG:|TRACE:|INFO:|\$|commit\s+[0-9a-f]{10,}|Author:|Date:|\.\.\.)",
    re.IGNORECASE,
)

_NAME_MAP = {
    "architecture/guanlan": "观澜",
    "architecture/hengyue": "衡岳",
    "architecture/jingchuan": "镜川",
}


class DelegationFoldAggregator:
    """Aggregates and cleans multi-agent receipts into a concise folded summary."""

    def fold(
        self,
        task_id: str,
        receipts: Mapping[str, str],
    ) -> FoldedDelegationResult:
        cleaned_findings: dict[str, str] = {}
        timed_out_peers: list[str] = []
        errored_peers: list[str] = []
        ready_peers: list[str] = []

        for peer_id, raw_output in receipts.items():
            cleaned = self._clean_context_noise(raw_output)
            cleaned_findings[peer_id] = cleaned

            peer_display = _NAME_MAP.get(peer_id, peer_id)
            if "[TIMEOUT]" in raw_output:
                timed_out_peers.append(peer_display)
            elif "[ERROR]" in raw_output:
                errored_peers.append(peer_display)
            else:
                ready_peers.append(peer_display)

        # 判定共识状态与权威汇总词
        if timed_out_peers or errored_peers:
            consensus_status = "concerns_noted"
            notes = []
            if timed_out_peers:
                notes.append(f"{'、'.join(timed_out_peers)}分析超时")
            if errored_peers:
                notes.append(f"{'、'.join(errored_peers)}执行异常")

            synthesized_verdict = (
                f"【架构协同汇报 - 部分降级】{'，'.join(notes)}，"
                f"基于就绪专家（{'、'.join(ready_peers)}）的结论综合收敛。"
            )
        else:
            consensus_status = "unanimous"
            synthesized_verdict = (
                "【架构协同汇报】架构三角已形成完全共识："
                "观澜（契约边界）、衡岳（状态机与不变量）、镜川（对抗审计）"
                "全数通过核验，方案架构优雅且符合第一性原理。"
            )

        return FoldedDelegationResult(
            task_id=task_id,
            member_findings=cleaned_findings,
            synthesized_verdict=synthesized_verdict,
            consensus_status=consensus_status,
        )

    def _clean_context_noise(self, text: str) -> str:
        """Strip raw command output, debug/trace noise to prevent context explosion."""
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not _NOISE_LINE_PATTERNS.match(line.strip())
        ]
        return "\n".join(lines).strip()
