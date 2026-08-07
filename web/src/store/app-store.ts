import { create } from "zustand";
import type { StampedEvent } from "../contracts";
import type { Conversation, TrackChoice, Turn, TurnStatus } from "../domain/conversation";
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
import type { Verbosity } from "../projectors";

export type ThemeMode = "light" | "dark";

interface AppSettings {
  readonly theme: ThemeMode;
  readonly verbosity: Verbosity;
  readonly developerMode: boolean;
  readonly mode: string;
  readonly track: TrackChoice;
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
  hydrate: () => Promise<void>;
  setTheme: (theme: ThemeMode) => void;
  setVerbosity: (verbosity: Verbosity) => void;
  setDeveloperMode: (enabled: boolean) => void;
  setMode: (mode: string) => void;
  setTrack: (track: TrackChoice) => void;
  setSidebarOpen: (open: boolean) => void;
  setError: (error: string | null) => void;
  newConversation: () => Promise<string>;
  selectConversation: (id: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
  appendTurn: (turn: Turn) => Promise<void>;
  updateActiveTurn: (patch: Partial<Turn>) => Promise<void>;
  setActiveRun: (runId: string | null, events?: readonly StampedEvent[]) => void;
  appendLiveEvent: (event: StampedEvent) => void;
  clearLiveEvents: () => void;
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
    mode: "board",
    track: "auto",
  },
  hydrated: false,
  sidebarOpen: true,
  error: null,
  activeRunId: null,
  liveEvents: [],

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
  },

  setTheme: (theme) => set((s) => ({ settings: { ...s.settings, theme } })),
  setVerbosity: (verbosity) => set((s) => ({ settings: { ...s.settings, verbosity } })),
  setDeveloperMode: (developerMode) =>
    set((s) => ({ settings: { ...s.settings, developerMode } })),
  setMode: (mode) => set((s) => ({ settings: { ...s.settings, mode } })),
  setTrack: (track) => set((s) => ({ settings: { ...s.settings, track } })),
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
    const conversations = get().conversations.filter((c) => c.id !== id);
    const activeConversationId =
      get().activeConversationId === id ? (conversations[0]?.id ?? null) : get().activeConversationId;
    await saveConversations(conversations);
    await saveActiveConversationId(activeConversationId);
    set({ conversations, activeConversationId, liveEvents: [], activeRunId: null });
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

  updateActiveTurn: async (patch) => {
    const activeId = get().activeConversationId;
    if (!activeId) return;
    const conversations = updateConversation(get().conversations, activeId, (c) => {
      if (c.turns.length === 0) return c;
      const turns = [...c.turns];
      const last = turns[turns.length - 1];
      turns[turns.length - 1] = { ...last, ...patch };
      return { ...c, turns };
    });
    await saveConversations(conversations);
    set({ conversations });
  },

  setActiveRun: (activeRunId, events) =>
    set({ activeRunId, liveEvents: events ?? get().liveEvents }),

  appendLiveEvent: (event) => set((s) => ({ liveEvents: [...s.liveEvents, event] })),

  clearLiveEvents: () => set({ liveEvents: [] }),
}));

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
