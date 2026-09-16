"""Runtime support plugins for hooks, middleware, and resume input.

Post-retirement (plan `docs/plans/2026-09-14-stop-decision-retirement.md`):
the State-cluster StopPolicy Provider is gone. The fixed `stop` phase
is replaced by the `terminal.commit` outer node; loop termination is
driven by `decision.action_type`, by `act.observe.terminate_decide` on an
unclassified host-side dispatch failure, and by the budget guard.
"""
