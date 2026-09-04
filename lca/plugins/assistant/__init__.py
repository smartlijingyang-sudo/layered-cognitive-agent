"""Assistant domain plugins (ADR-0187 §3 D6 + §7 PR-2..PR-8).

PR-4 范围装三个插件：

- ``lca.plugins.assistant.catalog`` —— Home CRUD + manifest digest 校验（PR-3）
- ``lca.plugins.assistant.bootstrap`` —— SOUL/IDENTITY/USER/AGENTS 投影进
  ContextManifest（PR-4）
- ``lca.plugins.assistant.workspace`` —— 物化 ExecutionSpace 事实（PR-4）

skill_overlay / jobs / evolve 由 PR-6/8 落地,本包暂不含。
"""
