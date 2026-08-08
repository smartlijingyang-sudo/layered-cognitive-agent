/**
 * Parse GeneratedFile metadata from tool / A2A payloads that appear in
 * journal ToolInvoked.result_preview (JSON) or similar structures.
 */

import type { GeneratedFile } from "../domain/generated-file";

const FILE_TOOL_NAMES = new Set(["write_file", "generate_file", "file_write"]);

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

export function isFileToolName(toolName: string): boolean {
  return FILE_TOOL_NAMES.has(toolName);
}

export function parseGeneratedFile(value: unknown): GeneratedFile | null {
  const record = asRecord(value);
  if (!record) return null;

  const name = record.name ?? record.filename;
  const mimeType = record.mimeType ?? record.mime_type ?? record.mediaType;
  if (typeof name !== "string" || !name.trim()) return null;
  if (typeof mimeType !== "string" || !mimeType.trim()) return null;

  const sizeRaw = record.sizeBytes ?? record.size_bytes ?? record.size;
  let sizeBytes: number | undefined;
  if (typeof sizeRaw === "number" && Number.isFinite(sizeRaw)) {
    sizeBytes = sizeRaw;
  } else if (typeof sizeRaw === "string" && sizeRaw.trim()) {
    const n = Number(sizeRaw);
    if (Number.isFinite(n)) sizeBytes = n;
  }

  const urlRaw = record.url ?? record.uri;
  const url = typeof urlRaw === "string" && urlRaw.trim() ? urlRaw : undefined;
  const previewable = Boolean(record.previewable);
  const previewHtml =
    typeof record.previewHtml === "string"
      ? record.previewHtml
      : typeof record.preview_html === "string"
        ? record.preview_html
        : undefined;

  return {
    name: name.trim(),
    mimeType: mimeType.trim(),
    sizeBytes,
    url,
    previewable: previewable || Boolean(previewHtml),
    previewHtml,
  };
}

/**
 * Extract zero or more GeneratedFile from a ToolInvoked-style result_preview string.
 */
export function filesFromToolResultPreview(
  toolName: string,
  resultPreview: string,
  ok: boolean,
): readonly GeneratedFile[] {
  if (!ok || !resultPreview.trim()) return [];
  if (!isFileToolName(toolName) && !resultPreview.includes("mimeType") && !resultPreview.includes("mime_type")) {
    // Still try parse if looks like a single file object
    if (!resultPreview.trimStart().startsWith("{")) return [];
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(resultPreview) as unknown;
  } catch {
    return [];
  }

  const single = parseGeneratedFile(parsed);
  if (single) return [single];

  const record = asRecord(parsed);
  if (record && Array.isArray(record.files)) {
    return record.files
      .map((item) => parseGeneratedFile(item))
      .filter((f): f is GeneratedFile => f !== null);
  }

  if (Array.isArray(parsed)) {
    return parsed
      .map((item) => parseGeneratedFile(item))
      .filter((f): f is GeneratedFile => f !== null);
  }

  return [];
}
