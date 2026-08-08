const STRUCTURAL_LINE =
  /^(#{1,6}\s|[-*+]\s|\d+\.\s|>\s|```|---|\|.+\|)/;

const SECTION_LINE =
  /^[✅📌🔹⭐▪️]\s*[一二三四五六七八九十\d]+[、.]|^[一二三四五六七八九十\d]+[、.]/;

function isStructuralBlock(block: string): boolean {
  const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
  if (lines.length === 0) return false;
  if (lines.some((line) => STRUCTURAL_LINE.test(line) || SECTION_LINE.test(line))) return true;
  if (block.includes("\n") && lines.length > 1) return true;
  if (block.startsWith("```")) return true;
  return false;
}

function boldListLabel(line: string): string {
  const bullet = line.match(/^(\s*[-*+]\s+)(.+)$/);
  if (!bullet) return line;
  const [, prefix, body] = bullet;
  const label = body.match(/^(.{1,32}[：:])\s*(.*)$/);
  if (label) {
    return `${prefix}**${label[1]}** ${label[2]}`.trimEnd();
  }
  return line;
}

function enhanceChatStructure(chunk: string): string {
  return chunk
    .split("\n")
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed) return "";

      if (SECTION_LINE.test(trimmed) && !trimmed.startsWith("#")) {
        return `### ${trimmed}`;
      }

      const leadingSpaces = line.match(/^(\s*)/)?.[1] ?? "";
      if (/^•\s+/.test(trimmed)) {
        const indent = leadingSpaces.length >= 2 ? leadingSpaces : "  ";
        return `${indent}- ${trimmed.slice(2)}`;
      }

      if (/^[-*+]\s+/.test(trimmed)) {
        return boldListLabel(`${leadingSpaces}${trimmed}`);
      }

      return line;
    })
    .join("\n")
    .replace(/\n{3,}/g, "\n\n");
}

function normalizeProseChunk(chunk: string, mergeShortParagraphs: boolean): string {
  const normalized = enhanceChatStructure(chunk)
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (!normalized) return "";

  if (!mergeShortParagraphs) return normalized;

  const blocks = normalized.split(/\n\n+/).map((b) => b.trim()).filter(Boolean);
  const merged: string[] = [];

  for (const block of blocks) {
    if (isStructuralBlock(block)) {
      merged.push(block);
      continue;
    }

    const prev = merged[merged.length - 1];
    const prevPlain = prev !== undefined && !isStructuralBlock(prev);
    if (prevPlain && block.length <= 180) {
      merged[merged.length - 1] = `${prev} ${block.replace(/\s+/g, " ").trim()}`;
      continue;
    }
    merged.push(block.replace(/\n+/g, " ").replace(/\s+/g, " ").trim());
  }

  return merged.join("\n\n");
}

/**
 * 聊天场景 Markdown 预处理：保留列表/标题结构，合并 LLM 乱打的空行段落。
 */
export function normalizeChatMarkdown(
  text: string,
  mode: "streaming" | "final" = "final",
): string {
  if (!text.trim()) return text;

  const mergeShort = mode === "final";
  const parts: string[] = [];
  const fenceRe = /(```[\s\S]*?```)/g;
  let lastIndex = 0;

  for (const match of text.matchAll(fenceRe)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      parts.push(normalizeProseChunk(text.slice(lastIndex, index), mergeShort));
    }
    parts.push(match[0]);
    lastIndex = index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(normalizeProseChunk(text.slice(lastIndex), mergeShort));
  }

  return parts.filter(Boolean).join("").trimEnd();
}
