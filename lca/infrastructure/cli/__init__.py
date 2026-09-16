"""LCA Ops — unified platform orchestration.

One package manages the entire LCA development platform:
the LCA kernel process (lca_kernel serve, ADR-0119 决定 4, owned by the
supervisor), LobeHub frontend, infrastructure, and agent daemon. The
single local entry point for the kernel is ``lca-ops kernel-restart``;
``lca-ops kernel_serve`` and ``lca-ops kernel-boot`` are retired.

Architecture:
    Service Protocol  — every managed component implements the same interface
    ServiceRegistry   — services self-register, commands discover them
    OpsConfig         — single YAML SSOT, pydantic-validated
    Pipeline          — commands are sequences of named steps
    Console           — human (rich) or agent (JSON) output

Three concerns, clearly separated:
    Lifecycle  — start / stop / restart  (process management)
    Setup      — ensure_ready            (idempotent preparation)
    Health     — state / heal            (observe and self-repair)
"""
