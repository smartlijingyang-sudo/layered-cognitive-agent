"""认知层记忆门控包：摄入模态门控与显著性反思过滤。"""

from __future__ import annotations

from .modality import ModalityResult, filter_ingestion_modality
from .salience import SalienceGate, SalienceVerdict

__all__ = [
    "ModalityResult",
    "SalienceGate",
    "SalienceVerdict",
    "filter_ingestion_modality",
]
