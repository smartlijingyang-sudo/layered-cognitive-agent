import { get, set, del, keys } from "idb-keyval";
import type { Conversation } from "./conversation";

const STORAGE_KEY = "lca.conversations.v1";
const ACTIVE_KEY = "lca.activeConversationId";

export async function loadConversations(): Promise<Conversation[]> {
  const stored = await get<Conversation[]>(STORAGE_KEY);
  return stored ?? [];
}

export async function saveConversations(conversations: readonly Conversation[]): Promise<void> {
  await set(STORAGE_KEY, [...conversations]);
}

export async function loadActiveConversationId(): Promise<string | null> {
  return (await get<string | null>(ACTIVE_KEY)) ?? null;
}

export async function saveActiveConversationId(id: string | null): Promise<void> {
  if (id) {
    await set(ACTIVE_KEY, id);
  } else {
    await del(ACTIVE_KEY);
  }
}

export async function clearLocalConversations(): Promise<void> {
  await del(STORAGE_KEY);
  await del(ACTIVE_KEY);
  const allKeys = await keys();
  for (const key of allKeys) {
    if (typeof key === "string" && key.startsWith("lca.")) {
      await del(key);
    }
  }
}
