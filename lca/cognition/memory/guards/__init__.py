"""认知层记忆门控包：摄入模态门控与显著性反思过滤。"""

from __future__ import annotations

from .firewall import MemoryTactFirewall
from .modality import ModalityResult, filter_ingestion_modality
from .salience import SalienceGate, SalienceVerdict

__all__ = [
    "MemoryTactFirewall",
    "ModalityResult",
    "SalienceGate",
    "SalienceVerdict",
    "filter_ingestion_modality",
]
