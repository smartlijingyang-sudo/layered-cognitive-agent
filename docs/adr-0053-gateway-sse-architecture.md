# ADR-0053: Gateway SSE 链路

**状态**: Superseded  
**日期**: 2026-08-12

现行说明：[docs/run-live.md](run-live.md)。

本文描述的 EventStream / timeline 投影已删除。聊天实时面是 Journal SSE：`POST /runs` + `GET /runs/{id}/live`，`event:` = Journal 类名。编号 0053 在正式 ADR 目录里是 [统一搜索平面](adr/0053-unified-search-plane.md)，与本文无关。
