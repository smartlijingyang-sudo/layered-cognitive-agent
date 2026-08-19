"""Guard plugins — Tier-3 middleware.

Loop intervention (loop_intervention_policy.py) and step budget
(budget_policy.py) are the two default guards. They're the only
place where we keep a `guards/` package because both plugins share
the same audit/rollback helper patterns in the future.
"""
