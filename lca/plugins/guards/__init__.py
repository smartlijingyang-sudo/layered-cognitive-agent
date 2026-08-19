"""Guards package — empty after cognitive-primitive v3 PR4.

The historical Tier-3 middleware guards are deleted.  Loop warning is
handled by ``DecisionGate`` (see ``repeat_tool_call``); budget is
enforced by ``StopRule``.  This package is kept empty so historical
imports of ``lca.plugins.guards`` continue to resolve.
"""
