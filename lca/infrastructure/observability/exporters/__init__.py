"""OTel 导出后端集合（Langfuse 桥已被新 ScorerFn 插件替代，详见 fact_scorer_langfuse）。

console / jsonl 人类视图与落盘已迁往 journal 投影器
（``journal/console_projector.py`` / ``journal/jsonl_projector.py``）；
memory 导出器直接用 OTel SDK 自带 ``InMemorySpanExporter``（注册表登记）。
"""

__all__: list[str] = []
