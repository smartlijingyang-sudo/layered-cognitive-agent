from lca.infrastructure.vocal.gate import GatedVocalGate


class ReplyFirstMiddleware:
    """Reply-First 承接提醒中间件：在用户在场且尚未 Ack 时提醒模型先发声。"""

    REMINDER_TEXT: str = (
        "\n\n[Reply-First 契约]: 用户正在等待。"
        "在调用任何复杂外部工具或执行耗时排查前，请务必先通过 send_message(type='text') "
        "发送一句简明承接语（如‘正在为你排查...’），防止用户端产生假死感。"
    )

    def augment_prompt(self, base_prompt: str, gate: GatedVocalGate) -> str:
        if not gate.wake_context.requires_reply_first:
            return base_prompt
        if gate.has_acked:
            return base_prompt
        return f"{base_prompt}{self.REMINDER_TEXT}"
