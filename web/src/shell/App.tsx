import { useCallback, useEffect, useMemo, useState } from "react";
import { JournalLog } from "../journal-log/journal-log";
import {
  ChatProjector,
  EMPTY_TURN_TIMELINE,
  MessageProjector,
  TraceProjector,
  TurnTimelineProjector,
} from "../projectors";
import type { MessageTurn } from "../projectors";
import { FetchSseTransport } from "../transport";
import { AppLayout } from "../components/layout/AppLayout";
import { ChatError, ChatMain } from "../components/layout/ChatMain";
import { ConversationSidebar } from "../components/sidebar/ConversationSidebar";
import { ThreadView } from "../components/thread/ThreadView";
import { MessageList } from "../components/thread/MessageList";
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
import { ATTACHMENT_ONLY_QUESTION } from "../components/composer/Composer";
import type { ChatState, TurnTimeline } from "../projectors";
import "./app.css";

export default function App() {
  const store = useAppStore();
  const conversation = activeConversation(store);
  const turn = activeTurn(store);
  const [llmAvailable, setLlmAvailable] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  const log = useMemo(() => new JournalLog(), []);
  const chatProjector = useMemo(() => new ChatProjector(), []);
  const turnTimelineProjector = useMemo(() => new TurnTimelineProjector(), []);
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
  const [liveTimeline, setLiveTimeline] = useState<TurnTimeline>(EMPTY_TURN_TIMELINE);

  // Feature flag: ?message-renderer URL param or localStorage key
  const useMessageRenderer = useMemo(() => {
    if (new URLSearchParams(window.location.search).has("message-renderer")) return true;
    return localStorage.getItem("message-renderer") === "true";
  }, []);

  const messageProjector = useMemo(() => new MessageProjector(), []);
  const [messageTurn, setMessageTurn] = useState<MessageTurn | null>(null);

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

  useEffect(() => {
    // Reset process timeline when switching conversations.
    turnTimelineProjector.reset();
    setLiveTimeline(EMPTY_TURN_TIMELINE);
    messageProjector.reset();
    setMessageTurn(null);
  }, [store.activeConversationId, turnTimelineProjector, messageProjector]);

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
      turnTimelineProjector.reset();
      setLiveTimeline(EMPTY_TURN_TIMELINE);
      traceProjector.reset();
      setTrace(traceProjector.snapshot());
      messageProjector.reset();
      setMessageTurn(null);
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
          question: question.trim() || ATTACHMENT_ONLY_QUESTION,
          mode,
          conversation_id: conversationId,
          attachment_ids: attachmentIds,
        });
        const pendingTurn = {
          ...createTurn(
            runId,
            traceId,
            question.trim() || ATTACHMENT_ONLY_QUESTION,
            mode,
          ),
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
          setLiveTimeline(turnTimelineProjector.onEvent(stamped));
          messageProjector.onEvent(stamped);
          setMessageTurn(messageProjector.buildTurn(runId));

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
          files: finalChat.files.length ? finalChat.files : undefined,
        });

        // Snapshot process journal for historical ProcessFold replay.
        const journalEvents = useAppStore.getState().liveEvents;
        if (journalEvents.length > 0) {
          await store.persistTurnJournal(runId, journalEvents);
        }

        if (attachments.length > 0 && attachmentIds.length === 0) {
          store.setError("附件未能上传，请检查网关是否在运行");
        }

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
      turnTimelineProjector,
      messageProjector,
      transport,
    ],
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

  const homeActive = store.activeConversationId == null;
  const emptyTopic =
    !homeActive && conversation != null && conversation.turns.length === 0;
  const composerLayout = homeActive ? "home" : emptyTopic ? "topic" : "chat";

  return (
    <AppLayout
      theme={store.settings.theme}
      onThemeChange={store.setTheme}
      llmAvailable={llmAvailable}
      developerMode={store.settings.developerMode}
      onDeveloperModeChange={store.setDeveloperMode}
      verbosity={store.settings.verbosity}
      onVerbosityChange={store.setVerbosity}
      chatTitle={homeActive ? undefined : emptyTopic ? "新话题" : conversation?.title}
      homeActive={homeActive}
      onHome={() => {
        void store.goHome();
        store.setSidebarOpen(false);
      }}
      sidebar={
        <ConversationSidebar
          conversations={store.conversations}
          activeId={store.activeConversationId}
          homeActive={homeActive}
          onSelect={(id) => {
            void store.selectConversation(id);
            store.setSidebarOpen(false);
          }}
          onHome={() => {
            void store.goHome();
            store.setSidebarOpen(false);
          }}
          onNew={() => void store.newConversation()}
          onDelete={(id) => void store.deleteConversation(id)}
          theme={store.settings.theme}
          onThemeChange={store.setTheme}
          llmAvailable={llmAvailable}
          developerMode={store.settings.developerMode}
          onDeveloperModeChange={store.setDeveloperMode}
          verbosity={store.settings.verbosity}
          onVerbosityChange={store.setVerbosity}
        />
      }
      main={
        <ChatMain
          homeLayout={homeActive || !conversation || conversation.turns.length === 0}
          homeColumn={homeActive}
          messages={
            <>
              {useMessageRenderer && messageTurn ? (
                <MessageList turn={messageTurn} />
              ) : (
                <ThreadView
                  conversation={homeActive ? null : conversation}
                  liveEvents={store.liveEvents}
                  liveTimeline={liveTimeline}
                  turnTimelines={store.turnTimelines}
                  trace={trace}
                  verbosity={store.settings.verbosity}
                  developerMode={store.settings.developerMode}
                  mode={store.settings.mode}
                  homeActive={homeActive}
                  onOpenModePicker={() => {
                    document.getElementById("lca-mode-picker-trigger")?.click();
                  }}
                />
              )}
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
              layout={composerLayout}
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
