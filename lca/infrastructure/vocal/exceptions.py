class VocalGateError(Exception):
    """声带硬闸基础异常。"""


class VocalGateAlreadyBlockedError(VocalGateError):
    """已挂起等待 Widget，同轮次严禁二次发声异常。"""


class UndeliveredTurnError(VocalGateError):
    """轮次收敛时未向用户交付实质性结果异常。"""
