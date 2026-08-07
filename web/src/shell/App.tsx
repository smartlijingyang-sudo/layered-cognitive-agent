import { useCallback, useEffect, useMemo, useState } from "react";
import { JournalLog } from "../journal-log/journal-log";
import { ChatProjector, TraceProjector, type Verbosity } from "../projectors";
import { FetchSseTransport } from "../transport";
import { TracePanel } from "../renderers/trace-panel";
import { TypewriterAnswer } from "../renderers/typewriter";
import "./app.css";

const MODES = ["board", "routing", "pipeline", "solo"] as const;
type TrackChoice = "auto" | "real" | "scripted";

async function fetchLlmStatus(): Promise<{ llmAvailable: boolean; defaultTrack: string }> {
  const response = await fetch("/health");
  if (!response.ok) {
    return { llmAvailable: false, defaultTrack: "scripted" };
  }
  const data = (await response.json()) as { llm_available?: boolean; default_track?: string };
  return {
    llmAvailable: Boolean(data.llm_available),
    defaultTrack: data.default_track ?? "scripted",
  };
}

async function createRun(question: string, mode: string, track?: string): Promise<string> {
  const body: Record<string, string> = { question, mode };
  if (track) body.track = track;
  const response = await fetch("/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { error?: string }).error ?? `HTTP ${response.status}`);
  }
  const data = (await response.json()) as { run_id: string };
  return data.run_id;
}

export default function App() {
  const [question, setQuestion] = useState("评估移动端新功能上线的风险，分别从技术与业务视角分析。");
  const [mode, setMode] = useState<string>("board");
  const [track, setTrack] = useState<TrackChoice>("auto");
  const [llmAvailable, setLlmAvailable] = useState<boolean | null>(null);
  const [verbosity, setVerbosity] = useState<Verbosity>("standard");
  const [traceOpen, setTraceOpen] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const log = useMemo(() => new JournalLog(), []);
  const chatProjector = useMemo(() => new ChatProjector(), []);
  const traceProjector = useMemo(() => new TraceProjector(verbosity), [verbosity]);
  const transport = useMemo(
    () =>
      new FetchSseTransport({
        onError: (err) => setError(err instanceof Error ? err.message : String(err)),
      }),
    [],
  );

  const [chat, setChat] = useState(chatProjector.snapshot());
  const [trace, setTrace] = useState(traceProjector.snapshot());
  const [events, setEvents] = useState(log.snapshot());

  useEffect(() => {
    void fetchLlmStatus().then(({ llmAvailable: ok }) => setLlmAvailable(ok));
  }, []);

  useEffect(() => {
    traceProjector.reset();
    setTrace(traceProjector.snapshot());
  }, [verbosity, traceProjector]);

  const subscribeLog = useCallback(() => {
    return log.subscribe((stamped) => {
      setEvents(log.snapshot());
      setChat(chatProjector.onEvent(stamped));
      setTrace(traceProjector.onEvent(stamped));
    });
  }, [log, chatProjector, traceProjector]);

  const handleSubmit = async () => {
    setError(null);
    setBusy(true);
    log.clear();
    chatProjector.start(question);
    setChat(chatProjector.snapshot());
    traceProjector.reset();
    setTrace(traceProjector.snapshot());
    setEvents([]);
    transport.resetCursor();
    try {
      const trackArg = track === "auto" ? undefined : track;
      const id = await createRun(question, mode, trackArg);
      setRunId(id);
      const unsub = subscribeLog();
      await transport.connect(id, (e) => log.append(e));
      unsub();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app">
      <header className="topbar">
        <h1>LCA · 团队协作可观测性</h1>
        <span className="subtitle">
          journal 事件 → SSE → JournalLog → 投影渲染
          {llmAvailable === null
            ? ""
            : llmAvailable
              ? " · LLM: 真实（LLM_API_KEY 已配置）"
              : " · LLM: 离线假 LLM（未检测到 LLM_API_KEY）"}
        </span>
      </header>

      <main className="layout">
        <section className="chat-column">
          <label className="field">
            <span>协作模式</span>
            <select value={mode} onChange={(e) => setMode(e.target.value)} disabled={busy}>
              {MODES.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>LLM</span>
            <select value={track} onChange={(e) => setTrack(e.target.value as TrackChoice)} disabled={busy}>
              <option value="auto">自动（有 Key 用真实 LLM）</option>
              <option value="real">强制真实 LLM</option>
              <option value="scripted">离线 scripted</option>
            </select>
          </label>

          <label className="field">
            <span>问题</span>
            <textarea
              rows={4}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              disabled={busy}
            />
          </label>

          <div className="toolbar">
            <button type="button" onClick={() => void handleSubmit()} disabled={busy || !question.trim()}>
              {busy ? "运行中…" : "提交 run"}
            </button>
            <label className="verbosity">
              Verbosity
              <select
                value={verbosity}
                onChange={(e) => setVerbosity(e.target.value as Verbosity)}
                disabled={busy}
              >
                <option value="minimal">minimal</option>
                <option value="standard">standard</option>
                <option value="verbose">verbose</option>
              </select>
            </label>
          </div>

          {error ? <div className="error">{error}</div> : null}
          {runId ? <div className="run-id">run_id: {runId}</div> : null}

          <div className="bubble user">
            <div className="bubble-label">问题</div>
            <p>{chat.question || question}</p>
          </div>

          <div className="bubble assistant">
            <div className="bubble-label">回答 · {chat.status}</div>
            <TypewriterAnswer text={chat.answer} active={chat.status === "running" || busy} />
          </div>

          <button type="button" className="trace-toggle" onClick={() => setTraceOpen((v) => !v)}>
            {traceOpen ? "收起运行轨迹" : "展开运行轨迹"}
          </button>
        </section>

        {traceOpen ? <TracePanel events={events} trace={trace} verbosity={verbosity} /> : null}
      </main>
    </div>
  );
}
