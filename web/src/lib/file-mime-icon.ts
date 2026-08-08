/**
 * Map MIME types / filenames to lucide-react icon names for file cards.
 * Pure data — components resolve the actual icon component.
 */

export type FileIconKind =
  | "image"
  | "pdf"
  | "code"
  | "table"
  | "text"
  | "archive"
  | "html"
  | "audio"
  | "video"
  | "file";

const MIME_PREFIX_RULES: ReadonlyArray<readonly [string, FileIconKind]> = [
  ["image/", "image"],
  ["audio/", "audio"],
  ["video/", "video"],
  ["text/html", "html"],
  ["text/csv", "table"],
  ["text/", "text"],
  ["application/pdf", "pdf"],
  ["application/json", "code"],
  ["application/javascript", "code"],
  ["application/typescript", "code"],
  ["application/xml", "code"],
  ["application/zip", "archive"],
  ["application/x-zip", "archive"],
  ["application/gzip", "archive"],
  ["application/x-tar", "archive"],
  ["application/vnd.ms-excel", "table"],
  ["application/vnd.openxmlformats-officedocument.spreadsheetml", "table"],
];

const EXT_RULES: ReadonlyArray<readonly [string, FileIconKind]> = [
  [".png", "image"],
  [".jpg", "image"],
  [".jpeg", "image"],
  [".gif", "image"],
  [".webp", "image"],
  [".svg", "image"],
  [".pdf", "pdf"],
  [".html", "html"],
  [".htm", "html"],
  [".csv", "table"],
  [".tsv", "table"],
  [".xlsx", "table"],
  [".xls", "table"],
  [".json", "code"],
  [".ts", "code"],
  [".tsx", "code"],
  [".js", "code"],
  [".py", "code"],
  [".go", "code"],
  [".rs", "code"],
  [".zip", "archive"],
  [".gz", "archive"],
  [".tar", "archive"],
  [".txt", "text"],
  [".md", "text"],
];

export function fileIconKind(mimeType: string, name?: string): FileIconKind {
  const mime = mimeType.toLowerCase();
  for (const [prefix, kind] of MIME_PREFIX_RULES) {
    if (mime === prefix || mime.startsWith(prefix)) {
      return kind;
    }
  }
  if (name) {
    const lower = name.toLowerCase();
    for (const [ext, kind] of EXT_RULES) {
      if (lower.endsWith(ext)) return kind;
    }
  }
  return "file";
}

export function formatByteSize(sizeBytes: number | undefined): string | undefined {
  if (sizeBytes === undefined || !Number.isFinite(sizeBytes) || sizeBytes < 0) {
    return undefined;
  }
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}
