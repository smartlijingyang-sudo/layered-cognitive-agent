export interface ConversationSummary {
  readonly conversation_id: string;
  readonly title: string;
  readonly created_at: number;
}

export interface ConversationDetail {
  readonly conversation_id: string;
  readonly title: string;
  readonly created_at: number;
  readonly turns: readonly {
    readonly turn_id: string;
    readonly run_id: string;
    readonly trace_id: string;
    readonly question: string;
    readonly mode: string;
    readonly track: string;
    readonly status: string;
    readonly created_at: number;
  }[];
}

export async function listConversations(): Promise<ConversationSummary[]> {
  const response = await fetch("/conversations");
  if (!response.ok) return [];
  const data = (await response.json()) as { conversations?: ConversationSummary[] };
  return data.conversations ?? [];
}

export async function createConversation(title = ""): Promise<ConversationDetail> {
  const response = await fetch("/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return (await response.json()) as ConversationDetail;
}

export async function fetchConversation(conversationId: string): Promise<ConversationDetail | null> {
  const response = await fetch(`/conversations/${conversationId}`);
  if (!response.ok) return null;
  return (await response.json()) as ConversationDetail;
}
