/** LLM 决策 JSON 提取 —— 与 lca/layer1_cognitive/brain/decision_parser.py 对齐。 */

const JSON_FENCE_RE = /```(?:json)?\s*\n?([\s\S]*?)\n?\s*```/;
const JSON_OBJECT_RE = /\{[\s\S]*\}/;
const RESPONSE_KEY_RE = /"(?:response_text|response|text)"\s*:\s*"/;

export function extractJsonBlock(raw: string): string {
  const fenced = raw.match(JSON_FENCE_RE);
  if (fenced?.[1]) return fenced[1].trim();
  const object = raw.match(JSON_OBJECT_RE);
  if (object?.[0]) return object[0];
  return raw.trim();
}

function decodeJsonStringContent(source: string, start: number): string {
  let out = "";
  let escaped = false;
  for (let i = start; i < source.length; i += 1) {
    const ch = source[i];
    if (escaped) {
      if (ch === "n") out += "\n";
      else if (ch === "t") out += "\t";
      else if (ch === "r") out += "\r";
      else out += ch;
      escaped = false;
      continue;
    }
    if (ch === "\\") {
      escaped = true;
      continue;
    }
    if (ch === '"') break;
    out += ch;
  }
  return out;
}

interface ExtractOptions {
  /** 流式未闭合 JSON 时也尝试提取 response_text 前缀。 */
  readonly allowPartial?: boolean;
}

/**
 * 从 LLM 原始输出（常为 Decision JSON）提取用户可见正文。
 * 完整 JSON 优先 JSON.parse；流式半截时用字符串解码兜底。
 */
export function extractUserFacingAnswer(raw: string, options: ExtractOptions = {}): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;

  const jsonBlock = extractJsonBlock(trimmed);

  if (!options.allowPartial) {
    try {
      const data = JSON.parse(jsonBlock) as Record<string, unknown>;
      const text = data.response_text ?? data.response ?? data.text;
      if (typeof text === "string" && text.trim()) return text;
      if (typeof text === "string") return text;
      return null;
    } catch {
      if (!options.allowPartial) return null;
    }
  }

  const keyMatch = jsonBlock.match(RESPONSE_KEY_RE);
  if (!keyMatch || keyMatch.index === undefined) return null;
  const valueStart = keyMatch.index + keyMatch[0].length;
  const decoded = decodeJsonStringContent(jsonBlock, valueStart);
  return decoded || null;
}

/** 展示层兜底：若文本像 Decision JSON，提取 response_text；否则原样返回。 */
export function sanitizeAssistantDisplayText(text: string, streaming = false): string {
  const trimmed = text.trim();
  if (!trimmed) return text;
  if (!trimmed.includes("response_text") && !trimmed.includes('"action_type"')) {
    return text;
  }
  const extracted = extractUserFacingAnswer(trimmed, { allowPartial: streaming });
  return extracted ?? text;
}
