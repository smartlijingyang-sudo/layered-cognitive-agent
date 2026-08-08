import { useCallback, useEffect, useMemo, useState } from "react";
import { JournalLog } from "../journal-log/journal-log";
import { ChatProjector, TraceProjector } from "../projectors";
import { FetchSseTransport } from "../transport";
import { AppLayout } from "../components/layout/AppLayout";
import { ChatError, ChatMain } from "../components/layout/ChatMain";
import { ConversationSidebar } from "../components/sidebar/ConversationSidebar";
import { ThreadView } from "../components/thread/ThreadView";
import { Composer } from "../components/composer/Composer";
import { DeveloperTracePanel } from "../components/trace/DeveloperTracePanel";
import { createRun, cancelRun, fetchHealth, fetchRunSummary } from "../api/runs";
import {
  FileApiNotAvailableError,
  uploadAttachment,
} from "../api/files";
import {
  activeConversation,
  activeTurn,
  mapRunStatus,
  useAppStore,
} from "../store/app-store";
import { createTurn } from "../domain/conversation";
import type { LocalAttachment } from "../domain/generated-file";
import { toPersistableAttachments } from "../domain/generated-file";
import { shouldPersistTurnOnEvent } from "../lib/persist-turn";
import type { ChatState } from "../projectors";
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
    async (
      question: string,
      modeOverride?: string,
      attachments: readonly LocalAttachment[] = [],
    ) => {
      store.setError(null);
      setBusy(true);
      const conversationId = await ensureConversation();
      const mode = modeOverride ?? store.settings.mode;
      log.clear();
      store.clearLiveEvents();
      chatProjector.start(question);
      traceProjector.reset();
      setTrace(traceProjector.snapshot());
      transport.resetCursor();

      try {
        const uploadedAttachments: LocalAttachment[] = [];
        const attachmentIds: string[] = [];
        for (const att of attachments) {
          if (att.ref?.attachmentId) {
            attachmentIds.push(att.ref.attachmentId);
            uploadedAttachments.push(att);
            continue;
          }
          if (!att.file) {
            uploadedAttachments.push(att);
            continue;
          }
          try {
            const ref = await uploadAttachment(conversationId, att.file);
            attachmentIds.push(ref.attachmentId);
            uploadedAttachments.push({
              ...att,
              status: "uploaded",
              ref,
              error: undefined,
            });
          } catch (err) {
            const message =
              err instanceof FileApiNotAvailableError
                ? "上传端点不可用，已跳过该附件"
                : err instanceof Error
                  ? err.message
                  : "上传失败";
            uploadedAttachments.push({ ...att, status: "error", error: message });
          }
        }

        const { run_id: runId, trace_id: traceId } = await createRun({
          question,
          mode,
          conversation_id: conversationId,
          attachment_ids: attachmentIds,
        });
        const pendingTurn = {
          ...createTurn(runId, traceId, question, mode),
          attachments: toPersistableAttachments(uploadedAttachments),
        };
        await store.appendTurn({ ...pendingTurn, status: "running" });
        store.setActiveRun(runId);

        const syncTurnFromChat = (nextChat: ChatState, stamped: import("../contracts").StampedEvent) => {
          const patch = {
            status: mapRunStatus(nextChat.status === "idle" ? "running" : nextChat.status),
            answer: nextChat.answer,
            answerDeltas: nextChat.answerDeltas,
            files: nextChat.files.length ? nextChat.files : undefined,
          };
          if (shouldPersistTurnOnEvent(stamped)) {
            void store.updateActiveTurn(patch);
          } else {
            store.patchActiveTurn(patch);
          }
        };

        const unsub = log.subscribe((stamped) => {
          store.appendLiveEvent(stamped);
          const prevChat = chatProjector.snapshot();
          const nextChat = chatProjector.onEvent(stamped);
          setTrace(traceProjector.onEvent(stamped));

          const turnChanged =
            prevChat.answer !== nextChat.answer ||
            prevChat.status !== nextChat.status ||
            prevChat.answerDeltas !== nextChat.answerDeltas;
          if (turnChanged) {
            syncTurnFromChat(nextChat, stamped);
          }
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
        <ChatMain
          messages={
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
              {store.error ? <ChatError>{store.error}</ChatError> : null}
            </>
          }
          footer={
            <Composer
              mode={store.settings.mode}
              onModeChange={store.setMode}
              onSubmit={(question, attachments) =>
                void handleSubmit(question, undefined, attachments)
              }
              onStop={() => void handleStop()}
              busy={busy}
              canStop={busy && Boolean(store.activeRunId ?? turn?.runId)}
              llmAvailable={llmAvailable}
              conversationId={store.activeConversationId ?? undefined}
            />
          }
        />
      }
      tracePanel={tracePanel}
      sidebarOpen={store.sidebarOpen}
      onSidebarToggle={() => store.setSidebarOpen(!store.sidebarOpen)}
    />
  );
}
