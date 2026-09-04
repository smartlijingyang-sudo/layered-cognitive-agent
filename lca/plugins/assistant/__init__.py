"""Assistant domain plugins (ADR-0187 §3 D6).

PR-3 范围内只有 ``lca.plugins.assistant.catalog`` 一个插件，提供
``assistant.catalog`` capability；其它 5 个插件（bootstrap / workspace /
skill_overlay / jobs / evolve）是 PR-4…PR-8 工作，本 PR 不创建空壳。
"""
