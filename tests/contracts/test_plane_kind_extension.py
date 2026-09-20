from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef


def test_existing_plane_kinds_unchanged() -> None:
    assert PlaneKind.MACHINE == "machine"
    assert PlaneKind.SANDBOX == "sandbox"


def test_pool_worker_added() -> None:
    assert PlaneKind.POOL_WORKER == "pool_worker"


def test_plane_ref_backward_compatible() -> None:
    """现有构造方式（不传 capability_summary）仍然有效。"""
    ref = PlaneRef(
        id="s-1",
        label="sandbox",
        kind=PlaneKind.SANDBOX,
        root="/tmp",
        outputs_dir="/tmp/out",
    )
    assert ref.kind == PlaneKind.SANDBOX
    assert ref.capability_summary == ()
