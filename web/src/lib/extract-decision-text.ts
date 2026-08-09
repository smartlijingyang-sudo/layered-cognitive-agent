/**
 * LLM 决策 JSON 提取 —— 流式预览用 mirror of backend Intent Shape（ADR-0045）。
 *
 * 权威路径：后端 DecisionParser 形状归一后写入 DecisionMade.response_text，
 * chat-projector 提交主线时优先消费该字段。本模块只服务：
 * 1. StepTextDelta 流式预览（parse 尚未完成时）
 * 2. 旧 journal / 无 response_text 事件的回退
 */

const JSON_FENCE_RE = /```(?:json)?\s*\n?([\s\S]*?)\n?\s*```/;
const JSON_OBJECT_RE = /\{[\s\S]*\}/;
const RESPONSE_KEY_RE = /"(?:response_text|response|text)"\s*:\s*"/;

/** 与 decision_shape._DEFAULT_RESPOND_PSEUDO_TOOLS 对齐 */
const RESPOND_PSEUDO_TOOLS = new Set(["respond", "response", "answer", "reply"]);

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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function firstString(data: Record<string, unknown>, keys: readonly string[]): string | null {
  for (const key of keys) {
    const value = data[key];
    if (typeof value === "string") return value;
  }
  return null;
}

function argumentBag(data: Record<string, unknown>): Record<string, unknown> {
  for (const key of ["arguments", "args", "parameters"] as const) {
    const bag = data[key];
    if (isRecord(bag)) return bag;
  }
  return {};
}

/**
 * 从完整 Decision JSON 对象提取用户可见正文（mirror backend hoist_response_text）。
 */
function responseTextFromObject(data: Record<string, unknown>): string | null {
  const bag = argumentBag(data);
  const top = firstString(data, ["response_text", "response", "text"]);
  if (top !== null) return top;
  return firstString(bag, ["response_text", "response", "text"]);
}

interface ExtractOptions {
  /** 流式未闭合 JSON 时也尝试提取 response_text 前缀。 */
  readonly allowPartial?: boolean;
}

/**
 * 从 LLM 原始输出（常为 Decision JSON）提取用户可见正文。
 * 完整 JSON 优先 JSON.parse + 形状感知 hoist；流式半截时用字符串解码兜底。
 */
export function extractUserFacingAnswer(raw: string, options: ExtractOptions = {}): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;

  const jsonBlock = extractJsonBlock(trimmed);

  try {
    const data = JSON.parse(jsonBlock) as unknown;
    if (isRecord(data)) {
      const text = responseTextFromObject(data);
      if (typeof text === "string" && text.trim()) return text;
      if (typeof text === "string") return text;
      // 能 parse 但无正文：例如纯 delegate JSON —— 不回退正则以免误抽
      return null;
    }
  } catch {
    // fall through to partial / regex path
  }

  if (!options.allowPartial) {
    // 完整模式：parse 失败则放弃（避免把半截当正文）
    // 但若明确含 response_text 键，仍尝试扫描（容错截断 JSON）
    if (!RESPONSE_KEY_RE.test(jsonBlock)) return null;
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
  // use_tool + pseudo respond 也视为决策 JSON
  const looksLikeDecision =
    trimmed.includes('"action_type"') ||
    [...RESPOND_PSEUDO_TOOLS].some((name) => trimmed.includes(`"tool_name": "${name}"`));
  if (!looksLikeDecision && !trimmed.includes("response_text")) {
    return text;
  }
  const extracted = extractUserFacingAnswer(trimmed, { allowPartial: streaming });
  return extracted ?? text;
}
