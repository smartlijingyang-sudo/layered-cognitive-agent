"""Assistant domain plugins (ADR-0187 §3 D6 + §7 PR-2..PR-8).

当前包含：

- ``lca.plugins.assistant.catalog`` —— Home CRUD + manifest digest 校验（PR-3）
- ``lca.plugins.assistant.bootstrap`` —— SOUL/IDENTITY/USER/AGENTS 投影进
  ContextManifest（PR-4）
- ``lca.plugins.assistant.workspace`` —— 物化 ExecutionSpace 事实（PR-4）
- ``lca.plugins.assistant.skill_overlay`` —— 0048 拉取 + 0067 三闸的
  skill 安装/激活（PR-6）
- ``lca.plugins.assistant.evolve`` —— SkillAcquirer 助理域对应物,实验候选 +
  审批提升（PR-8）
- ``lca.plugins.assistant.jobs`` —— JobSpec 收集 → ADR-0093 WorkQueue（PR-8）
"""
