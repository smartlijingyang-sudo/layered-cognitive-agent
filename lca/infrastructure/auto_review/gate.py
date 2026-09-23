from typing import Any

from lca.contracts.models.auto_review.models import (
    AutoReviewAction,
    AutoReviewMode,
    AutoReviewVerdict,
    compute_action_fingerprint,
)


class AutoReviewGate:
    """工具副作用自动审查硬闸。

    根据 ADR-0248 §3.5 规范：
    1. OFF 模式：无干预全部放行；
    2. SHADOW 模式：异步记录审计记录，不阻断执行；
    3. ENFORCE 模式：硬阻断高危操作；
       - Adapt 路径：提示更低权限的同目标路径；
       - Escalate 路径：基于确定性 SHA-256 动作指纹发起人审，放行后只允许同一动作不变重放，
         严禁换命令绕过；
       - 连接器/插件鉴权类工具（``mcp__*`` / connector 管理）一律升格人审，
         对应 ADR-0248 §3.5 的「连接器鉴权」闸。

    用户本机 OS 对话框（受保护目录、权限弹窗）由 ADR-0246 的审批链覆盖：
    ``MachineComputer._gate`` 对越界/敏感操作返回 ``approval_required``，
    经 ``ApprovalPolicyEngine`` 的 ``MachineAccessStrategy`` 走 HITL 审批，
    本硬闸不重复拦截。
    """

    DANGEROUS_COMMAND_SUBSTRINGS = ("rm -rf", "cat /etc/shadow", "mkfs", "> /dev/")
    #: 连接器/插件管理类工具名子串：装插件前需要用户 widget 同意（ADR-0248 §3.5）。
    HUMAN_GATE_TOOL_SUBSTRINGS = (
        "mcp__",
        "connector",
        "install_plugin",
        "enable_connector",
        "composio",
    )

    def __init__(self, mode: AutoReviewMode = AutoReviewMode.ENFORCE) -> None:
        self.mode = mode
        self._audit_records: list[dict[str, Any]] = []
        self._approved_fingerprints: set[str] = set()

    def grant_approval(self, fingerprint: str) -> None:
        """人工审批放行指定动作指纹。"""
        self._approved_fingerprints.add(fingerprint)

    def evaluate(self, tool_name: str, arguments: dict[str, Any]) -> AutoReviewVerdict:
        fp = compute_action_fingerprint(tool_name, arguments)

        # 检查是否已获得人审放行（Escalate 同一动作重放）
        if fp in self._approved_fingerprints:
            return AutoReviewVerdict(
                action=AutoReviewAction.ALLOW,
                reason="动作已由人工授权放行",
                action_fingerprint=fp,
            )

        cmd = str(arguments.get("command", ""))
        is_risky = any(sub in cmd for sub in self.DANGEROUS_COMMAND_SUBSTRINGS)

        if self.mode == AutoReviewMode.OFF:
            return AutoReviewVerdict(action=AutoReviewAction.ALLOW, reason="AutoReview 关闭")

        if self.mode == AutoReviewMode.SHADOW:
            self._audit_records.append({"tool": tool_name, "args": arguments, "flagged": is_risky})
            return AutoReviewVerdict(action=AutoReviewAction.ALLOW, reason="Shadow 模式放行并审计")

        # ENFORCE 模式
        # 连接器/插件鉴权：装插件前需要用户 widget 同意（ADR-0248 §3.5）。
        if self._is_human_gate_tool(tool_name):
            return AutoReviewVerdict(
                action=AutoReviewAction.ESCALATE,
                reason=f"连接器/插件鉴权需要用户确认：{tool_name}",
                action_fingerprint=fp,
            )

        if not is_risky:
            return AutoReviewVerdict(action=AutoReviewAction.ALLOW, reason="操作低风险自动放行")

        if "cat /etc/shadow" in cmd:
            return AutoReviewVerdict(
                action=AutoReviewAction.BLOCK, reason="严禁读取受限敏感系统凭据"
            )

        # 高危且需要人审
        return AutoReviewVerdict(
            action=AutoReviewAction.ESCALATE,
            reason=f"高风险操作拦截，需要人审审批：{tool_name}",
            action_fingerprint=fp,
        )

    def _is_human_gate_tool(self, tool_name: str) -> bool:
        lowered = (tool_name or "").lower()
        return any(sub in lowered for sub in self.HUMAN_GATE_TOOL_SUBSTRINGS)

    def get_audit_records(self) -> list[dict[str, Any]]:
        return list(self._audit_records)
