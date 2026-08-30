"""Run-loop driver registry + loop plugins (ADR-0062).

Architecture:

* :mod:`registry` hosts the ``RunLoopDriverRegistry`` on the
  ``cordis.Context``. The ``/runs`` HTTP carrier
  (``gateway/runs/execute.py``) is a thin caller: it reads the active
  driver via ``ctx.require("run_loop_driver_registry")`` and delegates to
  ``driver.execute(ctx, ...)``.
* :mod:`cognitive` registers the default driver into that registry.

Profiles swap drivers by enabling/disabling loop plugins. There is no
module-level singleton.
"""
