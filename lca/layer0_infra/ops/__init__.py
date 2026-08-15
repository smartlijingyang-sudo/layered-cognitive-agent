"""LCA Ops — unified platform orchestration.

One package manages the entire LCA development platform:
gateway, LobeHub frontend, infrastructure, and agent daemon.

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
