from lca.application.vocal.runtime_wiring import (
    RuntimeVocalContext,
    resolve_runtime_vocal,
)
from lca.contracts.models.vocal.models import VocalMode
from lca.infrastructure.vocal.gate import DirectVocalGate, GatedVocalGate


def test_resolve_runtime_vocal_default_is_direct():
    ctx = resolve_runtime_vocal(vocal_mode=None, operation_id="op_1")
    assert isinstance(ctx, RuntimeVocalContext)
    assert ctx.mode == VocalMode.DIRECT
    assert isinstance(ctx.gate, DirectVocalGate)
    assert ctx.settle_guard is None


def test_resolve_runtime_vocal_gated():
    ctx = resolve_runtime_vocal(vocal_mode="gated", operation_id="op_2")
    assert isinstance(ctx, RuntimeVocalContext)
    assert ctx.mode == VocalMode.GATED
    assert isinstance(ctx.gate, GatedVocalGate)
    assert ctx.settle_guard is not None
