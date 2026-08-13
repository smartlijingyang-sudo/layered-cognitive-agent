/** LobeHub sendMessage plants this until a real assistant body lands. */
export const ASSISTANT_PLACEHOLDER = '...';

export type ProjectedRow = {
  assistantId: string;
  content: string;
  hasReasoning: boolean;
  toolCount: number;
};

export type StoredRow = {
  content?: string | null;
  tools?: { length: number } | null;
};

export function isPlaceholderContent(content: unknown): boolean {
  if (typeof content !== 'string') return true;
  const text = content.trim();
  return text === '' || text === ASSISTANT_PLACEHOLDER;
}

export function persistMissed(memory: ProjectedRow, stored: StoredRow | undefined): boolean {
  if (!memory.assistantId) return false;
  if (!stored) return !isPlaceholderContent(memory.content) || memory.toolCount > 0;
  if (!isPlaceholderContent(memory.content) && isPlaceholderContent(stored.content)) return true;
  if (memory.toolCount > 0 && !(stored.tools && stored.tools.length > 0)) return true;
  return false;
}

export function snapshotRow(
  assistantId: string,
  content: string,
  toolCount: number,
  hasReasoning: boolean,
): ProjectedRow {
  return { assistantId, content, hasReasoning, toolCount };
}
