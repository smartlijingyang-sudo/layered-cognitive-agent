/** SSE 帧解析 —— fetch + ReadableStream，支持 Last-Event-ID 续传。 */

export interface SseMessage {
  readonly id?: string;
  readonly event?: string;
  readonly data: string;
}

export function parseSseChunk(buffer: string): { messages: SseMessage[]; rest: string } {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  const messages: SseMessage[] = [];
  for (const block of parts) {
    if (!block.trim()) continue;
    let id: string | undefined;
    let event: string | undefined;
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("id: ")) id = line.slice(4);
      else if (line.startsWith("event: ")) event = line.slice(7);
      else if (line.startsWith("data: ")) dataLines.push(line.slice(6));
      else if (line.startsWith(":")) continue;
    }
    if (dataLines.length > 0) {
      messages.push({ id, event, data: dataLines.join("\n") });
    }
  }
  return { messages, rest };
}
