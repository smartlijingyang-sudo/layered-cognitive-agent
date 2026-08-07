import { useCallback, useEffect, useMemo, useState } from "react";
import { JournalLog } from "../journal-log/journal-log";
import { ChatProjector, TraceProjector } from "../projectors";
import { FetchSseTransport } from "../transport";
import { AppLayout } from "../components/layout/AppLayout";
import { ConversationSidebar } from "../components/sidebar/ConversationSidebar";
import { ThreadView } from "../components/thread/ThreadView";
import { Composer } from "../components/composer/Composer";
import { DeveloperTracePanel } from "../components/trace/DeveloperTracePanel";
import { createRun, cancelRun, fetchHealth, fetchRunSummary } from "../api/runs";
import {
  activeConversation,
  activeTurn,
  mapRunStatus,
  useAppStore,
} from "../store/app-store";
import { createTurn } from "../domain/conversation";
import { cn } from "../lib/cn";
import { mutedText } from "../lib/ui";
import "./app.css";

export default function App() {
  const store = useAppStore();
  const conversation = activeConversation(store);
  const turn = activeTurn(store);
  const [llmAvailable, setLlmAvailable] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  const log = useMemo(() => new JournalLog(), []);
  const chatProjector = useMemo(() => new ChatProjector(), []);
  const traceProjector = useMemo(
    () => new TraceProjector(store.settings.verbosity),
    [store.settings.verbosity],
  );
  const transport = useMemo(
    () =>
      new FetchSseTransport({
        onError: (err) => {
          useAppStore
            .getState()
            .setError(err instanceof Error ? err.message : String(err));
        },
      }),
    [],
  );

  const [chat, setChat] = useState(chatProjector.snapshot());
  const [trace, setTrace] = useState(traceProjector.snapshot());

  useEffect(() => {
    document.documentElement.dataset.theme = store.settings.theme;
  }, [store.settings.theme]);

  useEffect(() => {
    void useAppStore.getState().hydrate();
    void fetchHealth().then(({ llmAvailable: ok }) => setLlmAvailable(ok));
  }, []);

  useEffect(() => {
    traceProjector.reset();
    setTrace(traceProjector.snapshot());
  }, [store.settings.verbosity, traceProjector]);

  const ensureConversation = useCallback(async () => {
    if (store.activeConversationId) return store.activeConversationId;
    return store.newConversation();
  }, [store]);

  const handleSubmit = useCallback(
    async (question: string, modeOverride?: string) => {
      store.setError(null);
      setBusy(true);
      const conversationId = await ensureConversation();
      const mode = modeOverride ?? store.settings.mode;
      log.clear();
      store.clearLiveEvents();
      chatProjector.start(question);
      setChat(chatProjector.snapshot());
      traceProjector.reset();
      setTrace(traceProjector.snapshot());
      transport.resetCursor();

      try {
        const { run_id: runId, trace_id: traceId } = await createRun({
          question,
          mode,
          conversation_id: conversationId,
        });
        const pendingTurn = createTurn(runId, traceId, question, mode);
        await store.appendTurn({ ...pendingTurn, status: "running" });
        store.setActiveRun(runId);

        const unsub = log.subscribe((stamped) => {
          store.appendLiveEvent(stamped);
          const nextChat = chatProjector.onEvent(stamped);
          setChat(nextChat);
          setTrace(traceProjector.onEvent(stamped));
          void store.updateActiveTurn({
            status: mapRunStatus(nextChat.status === "idle" ? "running" : nextChat.status),
            answer: nextChat.answer,
            answerDeltas: nextChat.answerDeltas,
          });
        });

        await transport.connect(runId, (event) => log.append(event));
        unsub();

        const finalChat = chatProjector.snapshot();
        let finalStatus = mapRunStatus(finalChat.status === "idle" ? "running" : finalChat.status);
        let finalAnswer = finalChat.answer;
        let finalError = finalChat.errorMessage;

        if (finalStatus === "running" || finalStatus === "pending") {
          const summary = await fetchRunSummary(runId);
          if (summary?.status === "failed") {
            finalStatus = "failed";
            finalError = summary.error ?? finalError ?? "运行失败";
          } else if (summary?.status === "completed") {
            finalStatus = "completed";
          } else if (summary?.status === "canceled") {
            finalStatus = "canceled";
          }
        }

        await store.updateActiveTurn({
          status: finalStatus,
          answer: finalAnswer,
          answerDeltas: finalChat.answerDeltas,
        });

        if (finalStatus === "failed" && finalError && !store.error) {
          store.setError(finalError);
        }
      } catch (error) {
        store.setError(error instanceof Error ? error.message : String(error));
        await store.updateActiveTurn({ status: "failed" });
      } finally {
        setBusy(false);
        store.setActiveRun(null);
      }
    },
    [
      chatProjector,
      ensureConversation,
      log,
      store,
      traceProjector,
      transport,
    ],
  );

  const handleExampleSelect = useCallback(
    (prompt: string, exampleMode: string) => {
      store.setMode(exampleMode);
      void handleSubmit(prompt, exampleMode);
    },
    [handleSubmit, store],
  );

  const handleStop = async () => {
    const runId = store.activeRunId ?? turn?.runId;
    if (!runId) return;
    try {
      await cancelRun(runId);
      await store.updateActiveTurn({ status: "canceled" });
    } catch (error) {
      store.setError(error instanceof Error ? error.message : String(error));
    }
  };

  const tracePanel =
    store.settings.developerMode && store.liveEvents.length > 0 ? (
      <DeveloperTracePanel
        events={store.liveEvents}
        trace={trace}
        verbosity={store.settings.verbosity}
      />
    ) : null;

  return (
    <AppLayout
      theme={store.settings.theme}
      onThemeChange={store.setTheme}
      llmAvailable={llmAvailable}
      developerMode={store.settings.developerMode}
      onDeveloperModeChange={store.setDeveloperMode}
      verbosity={store.settings.verbosity}
      onVerbosityChange={store.setVerbosity}
      sidebar={
        <ConversationSidebar
          conversations={store.conversations}
          activeId={store.activeConversationId}
          onSelect={(id) => {
            void store.selectConversation(id);
            store.setSidebarOpen(false);
          }}
          onNew={() => void store.newConversation()}
          onDelete={(id) => void store.deleteConversation(id)}
        />
      }
      main={
        <>
          <ThreadView
            conversation={conversation}
            liveEvents={store.liveEvents}
            trace={trace}
            verbosity={store.settings.verbosity}
            developerMode={store.settings.developerMode}
            mode={store.settings.mode}
            onExampleSelect={handleExampleSelect}
          />
          {store.error ? (
            <div
              className={cn(
                "rounded-[var(--radius-md)] border border-danger/35 bg-danger/10 px-3 py-2.5 text-danger",
              )}
            >
              {store.error}
            </div>
          ) : null}
          <Composer
            mode={store.settings.mode}
            onModeChange={store.setMode}
            onSubmit={(question) => void handleSubmit(question)}
            onStop={() => void handleStop()}
            busy={busy}
            canStop={busy && Boolean(store.activeRunId ?? turn?.runId)}
            llmAvailable={llmAvailable}
          />
          {!store.settings.developerMode && chat.phase !== "idle" ? (
            <p className={cn("text-sm", mutedText)}>
              运行阶段：{chat.phase === "completed" ? "已完成" : chat.phase === "failed" ? "失败" : "进行中"}
            </p>
          ) : null}
        </>
      }
      tracePanel={tracePanel}
      sidebarOpen={store.sidebarOpen}
      onSidebarToggle={() => store.setSidebarOpen(!store.sidebarOpen)}
    />
  );
}
