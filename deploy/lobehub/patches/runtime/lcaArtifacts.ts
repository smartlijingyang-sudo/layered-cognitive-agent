/** Journal file parts → final-answer native lists. */

export type ArtifactFile = {
  attachmentId?: string;
  mimeType: string;
  name: string;
  previewable: boolean;
  size?: number;
  url: string;
};

export type ImageRow = { alt: string; id: string; url: string };

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function basename(name: string): string {
  const parts = name.split(/[/\\]/);
  return parts.at(-1) || name;
}

export function isImageArtifact(file: ArtifactFile): boolean {
  return file.mimeType.startsWith('image/') || /\.(png|jpe?g|gif|webp|svg)$/i.test(file.name);
}

export function normalizeArtifactFile(raw: unknown): ArtifactFile | undefined {
  const rec = asRecord(raw);
  if (!rec) return undefined;
  const name = String(rec.name ?? rec.filename ?? '').trim();
  const url = String(rec.url ?? '').trim();
  if (!name || !url) return undefined;
  const mimeType = String(rec.mimeType ?? rec.mime_type ?? 'application/octet-stream');
  const sizeRaw = rec.sizeBytes ?? rec.size_bytes ?? rec.size;
  const size = typeof sizeRaw === 'number' && Number.isFinite(sizeRaw) ? sizeRaw : undefined;
  const attachmentId = String(rec.attachmentId ?? rec.attachment_id ?? '');
  const previewable =
    rec.previewable === true || rec.previewable === false
      ? Boolean(rec.previewable)
      : mimeType.startsWith('image/') || mimeType === 'application/pdf';
  return {
    mimeType,
    name,
    previewable,
    url,
    ...(attachmentId ? { attachmentId } : {}),
    ...(size !== undefined ? { size } : {}),
  };
}

export function collectArtifactFiles(...sources: unknown[]): ArtifactFile[] {
  const out: ArtifactFile[] = [];
  const seen = new Set<string>();
  for (const source of sources) {
    const list = Array.isArray(source) ? source : [];
    for (const item of list) {
      const file = normalizeArtifactFile(item);
      if (!file) continue;
      const key = `${file.url}|${file.name}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(file);
    }
  }
  return out;
}

export function latestDeliverables(files: ArtifactFile[]): ArtifactFile[] {
  const byName = new Map<string, ArtifactFile>();
  for (const file of files) {
    byName.set(basename(file.name), file);
  }
  return [...byName.values()];
}

/** Answer-bubble download list — same shape as the backend ledger closure. */
const CLOSURE_HEADING = '已生成以下文件：';

/**
 * Append the deliverable list to the answer text.
 *
 * `fileList` lives only in the store (LobeHub derives it from the
 * `messages_files` relation, which LCA's `/files` artifacts are not part of),
 * so the persisted answer text is what still carries the download after a
 * reload. The file list arrives on ``agent_runtime_end.data.artifactClosure``
 * (see ``deliverables.collectClosure``).
 */
export function appendDeliverableClosure(text: string, files: ArtifactFile[]): string {
  const missing = latestDeliverables(files).filter((file) => !text.includes(file.url));
  if (!missing.length) return text;
  const lines = missing.map((file) => `- [📥 ${file.name}](${file.url})`);
  const closure = [CLOSURE_HEADING, ...lines].join('\n');
  return text.trim() ? `${text.trimEnd()}\n\n${closure}` : closure;
}

export function toImageList(files: ArtifactFile[]): ImageRow[] {
  return latestDeliverables(files)
    .filter(isImageArtifact)
    .map((file) => ({
      alt: file.name,
      id: file.attachmentId || file.url,
      url: file.url,
    }));
}

export type FileRow = {
  fileType: string;
  id: string;
  name: string;
  size: number;
  url: string;
};

export function toFileList(files: ArtifactFile[]): FileRow[] {
  return latestDeliverables(files)
    .filter((file) => !isImageArtifact(file))
    .map((file) => ({
      fileType: file.mimeType,
      id: file.attachmentId || file.url,
      name: file.name,
      size: file.size ?? 0,
      url: file.url,
    }));
}
