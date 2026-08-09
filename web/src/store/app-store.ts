import { create } from "zustand";
import type { StampedEvent } from "../contracts";
import { AUTO_MODE_KEY } from "../contracts/modes.generated";
import type { Conversation, Turn, TurnStatus } from "../domain/conversation";
import {
  createConversation,
  conversationTitle,
} from "../domain/conversation";
import { newLocalId } from "../domain/ids";
import {
  loadActiveConversationId,
  loadConversations,
  saveActiveConversationId,
  saveConversations,
} from "../domain/conversation-store";
import {
  deleteTurnJournals,
  loadTurnJournal,
  saveTurnJournal,
} from "../domain/turn-journal-store";
import type { TurnTimeline, Verbosity } from "../projectors";
import { buildTurnTimeline, EMPTY_TURN_TIMELINE } from "../projectors";

export type ThemeMode = "light" | "dark";

interface AppSettings {
  readonly theme: ThemeMode;
  readonly verbosity: Verbosity;
  readonly developerMode: boolean;
  readonly mode: string;
}

interface AppState {
  readonly conversations: readonly Conversation[];
  readonly activeConversationId: string | null;
  readonly settings: AppSettings;
  readonly hydrated: boolean;
  readonly sidebarOpen: boolean;
  readonly error: string | null;
  readonly activeRunId: string | null;
  readonly liveEvents: readonly StampedEvent[];
  /** Historical turn timelines keyed by runId (from persisted journals). */
  readonly turnTimelines: Readonly<Record<string, TurnTimeline>>;
  hydrate: () => Promise<void>;
  setTheme: (theme: ThemeMode) => void;
  setVerbosity: (verbosity: Verbosity) => void;
  setDeveloperMode: (enabled: boolean) => void;
  setMode: (mode: string) => void;
  setSidebarOpen: (open: boolean) => void;
  setError: (error: string | null) => void;
  newConversation: () => Promise<string>;
  selectConversation: (id: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
  appendTurn: (turn: Turn) => Promise<void>;
  /** 仅更新内存态，不写 IndexedDB（流式过程中的高频 patch）。 */
  patchActiveTurn: (patch: Partial<Turn>) => void;
  updateActiveTurn: (patch: Partial<Turn>) => Promise<void>;
  setActiveRun: (runId: string | null, events?: readonly StampedEvent[]) => void;
  appendLiveEvent: (event: StampedEvent) => void;
  clearLiveEvents: () => void;
  /** Persist SSE journal for a finished turn and cache its timeline projection. */
  persistTurnJournal: (runId: string, events: readonly StampedEvent[]) => Promise<void>;
  ensureTurnTimelines: (runIds: readonly string[]) => Promise<void>;
}

function updateConversation(
  conversations: readonly Conversation[],
  id: string,
  updater: (conversation: Conversation) => Conversation,
): Conversation[] {
  return conversations.map((c) => (c.id === id ? updater(c) : c));
}

export const useAppStore = create<AppState>((set, get) => ({
  conversations: [],
  activeConversationId: null,
  settings: {
    theme: "dark",
    verbosity: "standard",
    developerMode: false,
    mode: AUTO_MODE_KEY,
  },
  hydrated: false,
  sidebarOpen: true,
  error: null,
  activeRunId: null,
  liveEvents: [],
  turnTimelines: {},

  hydrate: async () => {
    const conversations = await loadConversations();
    let activeId = await loadActiveConversationId();
    if (activeId && !conversations.some((c) => c.id === activeId)) {
      activeId = conversations[0]?.id ?? null;
    }
    if (!activeId && conversations.length > 0) {
      activeId = conversations[0]?.id ?? null;
    }
    set({ conversations, activeConversationId: activeId, hydrated: true });
    const runIds = conversations.flatMap((c) => c.turns.map((t) => t.runId));
    await get().ensureTurnTimelines(runIds);
  },

  setTheme: (theme) => set((s) => ({ settings: { ...s.settings, theme } })),
  setVerbosity: (verbosity) => set((s) => ({ settings: { ...s.settings, verbosity } })),
  setDeveloperMode: (developerMode) =>
    set((s) => ({ settings: { ...s.settings, developerMode } })),
  setMode: (mode) => set((s) => ({ settings: { ...s.settings, mode } })),
  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
  setError: (error) => set({ error }),

  newConversation: async () => {
    const id = newLocalId();
    const conversation = createConversation(id);
    const conversations = [conversation, ...get().conversations];
    await saveConversations(conversations);
    await saveActiveConversationId(id);
    set({ conversations, activeConversationId: id });
    return id;
  },

  selectConversation: async (id) => {
    await saveActiveConversationId(id);
    set({ activeConversationId: id, liveEvents: [], activeRunId: null });
  },

  deleteConversation: async (id) => {
    const removed = get().conversations.find((c) => c.id === id);
    const conversations = get().conversations.filter((c) => c.id !== id);
    const activeConversationId =
      get().activeConversationId === id ? (conversations[0]?.id ?? null) : get().activeConversationId;
    await saveConversations(conversations);
    await saveActiveConversationId(activeConversationId);
    if (removed) {
      await deleteTurnJournals(removed.turns.map((t) => t.runId));
    }
    const nextTimelines = { ...get().turnTimelines };
    for (const turn of removed?.turns ?? []) {
      delete nextTimelines[turn.runId];
    }
    set({
      conversations,
      activeConversationId,
      liveEvents: [],
      activeRunId: null,
      turnTimelines: nextTimelines,
    });
  },

  appendTurn: async (turn) => {
    const activeId = get().activeConversationId;
    if (!activeId) return;
    const conversations = updateConversation(get().conversations, activeId, (c) => {
      const title = c.turns.length === 0 ? conversationTitle(turn.question) : c.title;
      return { ...c, title, turns: [...c.turns, turn] };
    });
    await saveConversations(conversations);
    set({ conversations });
  },

  patchActiveTurn: (patch) => {
    const activeId = get().activeConversationId;
    if (!activeId) return;
    set({
      conversations: updateConversation(get().conversations, activeId, (c) => {
        if (c.turns.length === 0) return c;
        const turns = [...c.turns];
        const last = turns[turns.length - 1];
        turns[turns.length - 1] = { ...last, ...patch };
        return { ...c, turns };
      }),
    });
  },

  updateActiveTurn: async (patch) => {
    get().patchActiveTurn(patch);
    await saveConversations(get().conversations);
  },

  setActiveRun: (activeRunId, events) =>
    set({ activeRunId, liveEvents: events ?? get().liveEvents }),

  appendLiveEvent: (event) => set((s) => ({ liveEvents: [...s.liveEvents, event] })),

  clearLiveEvents: () => set({ liveEvents: [] }),

  persistTurnJournal: async (runId, events) => {
    if (!runId || events.length === 0) return;
    await saveTurnJournal(runId, events);
    const timeline = buildTurnTimeline(events);
    set((s) => ({
      turnTimelines: { ...s.turnTimelines, [runId]: timeline },
    }));
  },

  ensureTurnTimelines: async (runIds) => {
    const missing = runIds.filter((id) => id && !get().turnTimelines[id]);
    if (!missing.length) return;
    const loaded: Record<string, TurnTimeline> = {};
    await Promise.all(
      missing.map(async (runId) => {
        const events = await loadTurnJournal(runId);
        if (events?.length) {
          loaded[runId] = buildTurnTimeline(events);
        }
      }),
    );
    if (Object.keys(loaded).length === 0) return;
    set((s) => ({ turnTimelines: { ...s.turnTimelines, ...loaded } }));
  },
}));

export function turnTimelineFor(
  state: AppState,
  runId: string,
): TurnTimeline | undefined {
  return state.turnTimelines[runId];
}

export { EMPTY_TURN_TIMELINE };

export function activeConversation(state: AppState): Conversation | null {
  if (!state.activeConversationId) return null;
  return state.conversations.find((c) => c.id === state.activeConversationId) ?? null;
}

export function activeTurn(state: AppState): Turn | null {
  const conversation = activeConversation(state);
  if (!conversation || conversation.turns.length === 0) return null;
  return conversation.turns[conversation.turns.length - 1] ?? null;
}

export function mapRunStatus(status: string): TurnStatus {
  if (status === "completed") return "completed";
  if (status === "failed") return "failed";
  if (status === "canceled") return "canceled";
  if (status === "running") return "running";
  return "pending";
}
