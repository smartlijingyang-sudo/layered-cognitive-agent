/**
 * Parse GeneratedFile metadata from ToolInvoked.files (preferred) or
 * result_preview JSON (legacy fallback when structured field missing).
 */

import type { GeneratedFile } from "../domain/generated-file";
import { fileIconKind } from "./file-mime-icon";

const FILE_TOOL_NAMES = new Set([
  "write_file",
  "generate_file",
  "file_write",
  "run_sandbox_code",
]);

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

export function isFileToolName(toolName: string): boolean {
  return FILE_TOOL_NAMES.has(toolName);
}

/** Infer previewable when backend omits the flag (older journals). */
function inferPreviewable(mimeType: string, name: string, explicit?: boolean): boolean {
  if (explicit === true) return true;
  if (explicit === false) {
    // Still allow image/markdown/html preview by kind when url exists.
    const kind = fileIconKind(mimeType, name);
    return kind === "image" || kind === "html" || kind === "text" || kind === "code" || kind === "table";
  }
  const kind = fileIconKind(mimeType, name);
  return (
    kind === "image" ||
    kind === "html" ||
    kind === "text" ||
    kind === "code" ||
    kind === "table" ||
    mimeType.toLowerCase().startsWith("text/")
  );
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
  const explicitPreview =
    typeof record.previewable === "boolean" ? record.previewable : undefined;
  const previewHtml =
    typeof record.previewHtml === "string"
      ? record.previewHtml
      : typeof record.preview_html === "string"
        ? record.preview_html
        : undefined;
  const attachmentIdRaw = record.attachmentId ?? record.attachment_id;
  const attachmentId =
    typeof attachmentIdRaw === "string" && attachmentIdRaw.trim()
      ? attachmentIdRaw.trim()
      : undefined;

  const trimmedName = name.trim();
  const trimmedMime = mimeType.trim();

  return {
    name: trimmedName,
    mimeType: trimmedMime,
    sizeBytes,
    url,
    attachmentId,
    previewable: Boolean(previewHtml) || inferPreviewable(trimmedMime, trimmedName, explicitPreview),
    previewHtml,
  };
}

/**
 * Preferred path: ToolInvoked.files structured field (not truncated by journal policy).
 */
export function filesFromToolFilesField(
  files: readonly unknown[] | undefined | null,
  ok: boolean,
): readonly GeneratedFile[] {
  if (!ok || !files?.length) return [];
  return files
    .map((item) => parseGeneratedFile(item))
    .filter((f): f is GeneratedFile => f !== null);
}

/**
 * Legacy fallback: parse result_preview JSON (may be truncated / invalid).
 */
export function filesFromToolResultPreview(
  toolName: string,
  resultPreview: string,
  ok: boolean,
): readonly GeneratedFile[] {
  if (!ok || !resultPreview.trim()) return [];
  if (
    !isFileToolName(toolName) &&
    !resultPreview.includes("mimeType") &&
    !resultPreview.includes("mime_type")
  ) {
    if (!resultPreview.trimStart().startsWith("{") && !resultPreview.trimStart().startsWith("[")) {
      return [];
    }
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

/**
 * Merge structured files with legacy preview parse (structured wins / first).
 */
export function filesFromToolInvoked(args: {
  readonly toolName: string;
  readonly resultPreview: string;
  readonly ok: boolean;
  readonly files?: readonly unknown[] | null;
}): readonly GeneratedFile[] {
  const structured = filesFromToolFilesField(args.files, args.ok);
  if (structured.length) return structured;
  return filesFromToolResultPreview(args.toolName, args.resultPreview, args.ok);
}
