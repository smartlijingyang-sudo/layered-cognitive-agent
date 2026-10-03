// LCA-P1: module-level store for `reaction_added` gateway events.
//
// The backend EventTranslator emits `reaction_added` wire events with
// snake_case fields (`message_id`, `emoji`, `actor`); the gateway event
// handler records them here. Message bubbles subscribe through
// `useSyncExternalStore` and render aggregated emoji badges.
//
// Dependency-free on purpose so it can be unit-tested standalone.

export interface MessageReaction {
  message_id: string;
  emoji: string;
  actor: string;
}

export interface ReactionCount {
  emoji: string;
  count: number;
}

const reactionsByMessage = new Map<string, Map<string, ReactionCount>>();
const seenByMessage = new Map<string, Set<string>>();
const listeners = new Set<() => void>();
let version = 0;

const notify = () => {
  version += 1;
  for (const listener of listeners) listener();
};

/**
 * Record a `reaction_added` event. Identical `(message_id, emoji, actor)`
 * repeats are ignored so redelivered wire events cannot double-count.
 */
export const addReaction = ({ message_id, emoji, actor }: MessageReaction): void => {
  if (!message_id || !emoji) return;

  const seen = seenByMessage.get(message_id) ?? new Set<string>();
  const dedupeKey = `${emoji}\u0000${actor}`;
  if (seen.has(dedupeKey)) return;
  seen.add(dedupeKey);
  seenByMessage.set(message_id, seen);

  const byEmoji = reactionsByMessage.get(message_id) ?? new Map<string, ReactionCount>();
  const existing = byEmoji.get(emoji);
  byEmoji.set(emoji, existing ? { ...existing, count: existing.count + 1 } : { emoji, count: 1 });
  reactionsByMessage.set(message_id, byEmoji);

  notify();
};

/** Reactions for one message, in first-seen emoji order. */
export const getReactions = (messageId: string): ReactionCount[] => {
  const byEmoji = reactionsByMessage.get(messageId);
  return byEmoji ? Array.from(byEmoji.values()) : [];
};

/** `useSyncExternalStore` subscription. */
export const subscribe = (listener: () => void): (() => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

/** `useSyncExternalStore` snapshot: a monotonic version counter. */
export const getSnapshot = (): number => version;

/** Clear all state (test isolation). */
export const reset = (): void => {
  reactionsByMessage.clear();
  seenByMessage.clear();
  listeners.clear();
  version = 0;
};