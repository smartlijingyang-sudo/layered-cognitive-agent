"""DSH device-gateway wire message types (Phase 2 streaming).

Gateway ↔ daemon WebSocket carriers for real-time notification push.
Daemon runs the SDK locally; gateway projects notifications into Journal/SSE.
"""

from __future__ import annotations

# Server → client (gateway → daemon)
DSH_RUN_TURN_REQUEST = "dsh_run_turn_request"
DSH_CANCEL_TURN = "dsh_cancel_turn"

# Client → server (daemon → gateway)
DSH_NOTIFICATION = "dsh_notification"
DSH_TURN_FINISHED = "dsh_turn_finished"

# Daemon worker stdout (Python subprocess ↔ Node relay), not on WS wire
WORKER_KIND_NOTIFICATION = "notification"
WORKER_KIND_FINISHED = "finished"
WORKER_KIND_ERROR = "error"
