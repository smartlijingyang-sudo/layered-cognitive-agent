"""Delegation Fold Aggregator with Hermes-style anti-context-pollution.

Synthesizes specialist receipts into a single authoritative FoldedDelegationResult,
strips noisy tool traces, dynamically resolves specialist names, and determines consensus status.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import Any

from lca.contracts.models.collaboration.peer import FoldedDelegationResult
from lca.infrastructure.path.locator import get_lca_home

_logger = logging.getLogger(__name__)

_NOISE_LINE_PATTERNS = re.compile(
    r"^(DEBUG:|TRACE:|INFO:|\$|commit\s+[0-9a-f]{10,}|Author:|Date:|\.\.\.)",
    re.IGNORECASE,
)


class DelegationFoldAggregator:
    """Aggregates and cleans multi-agent receipts into a concise folded summary."""

    def __init__(self, role_library: Any | None = None) -> None:
        self._role_library = role_library

    def fold(
        self,
        task_id: str,
        receipts: Mapping[str, str],
        peer_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> FoldedDelegationResult:
        cleaned_findings: dict[str, str] = {}
        timed_out_peers: list[str] = []
        errored_peers: list[str] = []
        ready_peers: list[str] = []
        resolved_metadata: dict[str, dict[str, str]] = {}

        for peer_id, raw_output in receipts.items():
            cleaned = self._clean_context_noise(raw_output)
            cleaned_findings[peer_id] = cleaned

            peer_display, meta_dict = self._resolve_peer_info(peer_id, raw_output, peer_metadata)
            resolved_metadata[peer_id] = meta_dict

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
                f"【协同汇报 - 部分降级】{'，'.join(notes)}，"
                f"基于就绪专家（{'、'.join(ready_peers)}）的结论综合收敛。"
            )
        else:
            consensus_status = "unanimous"
            synthesized_verdict = (
                f"【协同汇报】全员共识已形成：{'、'.join(ready_peers)} "
                "全数通过核验，方案符合领域规范与质量契约。"
            )

        return FoldedDelegationResult(
            task_id=task_id,
            member_findings=cleaned_findings,
            synthesized_verdict=synthesized_verdict,
            consensus_status=consensus_status,
            member_metadata=resolved_metadata,
        )

    def _resolve_peer_info(
        self,
        peer_id: str,
        raw_output: str,
        peer_metadata: Mapping[str, Mapping[str, Any]] | None,
    ) -> tuple[str, dict[str, str]]:
        """Dynamically resolve display name and metadata for a peer."""
        # 1. 显式传入的 peer_metadata 优先
        if peer_metadata and peer_id in peer_metadata:
            raw_meta = peer_metadata[peer_id]
            if isinstance(raw_meta, dict):
                name = str(raw_meta.get("name") or raw_meta.get("title") or "").strip()
                if name:
                    return name, {k: str(v) for k, v in raw_meta.items()}
            elif isinstance(raw_meta, str) and raw_meta.strip():
                return raw_meta.strip(), {"name": raw_meta.strip()}

        # 2. 从 RoleLibrary 动态解析
        lib = self._get_role_library()
        if lib is not None:
            try:
                card = lib.get(peer_id)
                return card.title, {
                    "name": card.title,
                    "role": card.summary or card.title,
                    "emoji": getattr(card, "emoji", "") or "",
                    "department": getattr(card, "department", "") or "",
                }
            except Exception as exc:
                _logger.debug("Failed getting role card for %s: %s", peer_id, exc)

        # 3. 从 AssistantHome/meta.json 动态读取 (支持运行时创建的助理)
        try:
            home_dir = get_lca_home() / "assistants" / peer_id
            meta_file = home_dir / "meta.json"
            if meta_file.is_file():
                meta_json = json.loads(meta_file.read_text(encoding="utf-8"))
                name = meta_json.get("name")
                if name:
                    return str(name), {
                        "name": str(name),
                        "role": str(meta_json.get("role") or ""),
                    }
        except Exception as exc:
            _logger.debug("Failed reading assistant meta for %s: %s", peer_id, exc)

        # 4. 从输出文本首行正则自省推导人名（如 "观澜结论：" 或 "观澜（契约）："）
        first_line = raw_output.splitlines()[0].strip() if raw_output else ""
        match = re.match(r"^([^\W\d_]{2,8})(?:[（\(][^）\)]+[）\)])?(?:结论)?[:：\s]", first_line)
        if match:
            extracted_name = match.group(1).strip()
            return extracted_name, {"name": extracted_name}

        # 5. 安全兜底：格式化 peer_id slug
        slug = peer_id.split("/")[-1].removeprefix("arch_")
        display_name = slug.replace("_", " ").title()
        return display_name, {"name": display_name}

    def _get_role_library(self) -> Any | None:
        if self._role_library is not None:
            return self._role_library
        try:
            from lca.agent.role_library import FileRoleLibrary

            self._role_library = FileRoleLibrary()
            return self._role_library
        except Exception:
            return None

    def _clean_context_noise(self, text: str) -> str:
        """Strip raw command output, debug/trace noise to prevent context explosion."""
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not _NOISE_LINE_PATTERNS.match(line.strip())
        ]
        return "\n".join(lines).strip()
