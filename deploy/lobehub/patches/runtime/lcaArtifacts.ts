/** Journal file parts → LobeHub image/file rows and markdown hrefs. */

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

/** User-facing cards: one slot per basename, last harvest wins. */
const FILE_MD_RE = /\[(?:📥\s*)?([^\]]+)\]\((\/files\/file_[a-f0-9]+)\)/gi;

function mimeFromName(name: string): string {
  const lower = name.toLowerCase();
  if (lower.endsWith('.png')) return 'image/png';
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg';
  if (lower.endsWith('.gif')) return 'image/gif';
  if (lower.endsWith('.webp')) return 'image/webp';
  if (lower.endsWith('.svg')) return 'image/svg+xml';
  if (lower.endsWith('.pdf')) return 'application/pdf';
  if (lower.endsWith('.html') || lower.endsWith('.htm')) return 'text/html';
  if (lower.endsWith('.pptx')) {
    return 'application/vnd.openxmlformats-officedocument.presentationml.presentation';
  }
  if (lower.endsWith('.docx')) {
    return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
  }
  if (lower.endsWith('.xlsx')) {
    return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
  }
  return 'application/octet-stream';
}

/** Ledger closure markdown is the user-facing Work list (one card per basename). */
export function collectMarkdownDeliverables(text: string): ArtifactFile[] {
  if (!text) return [];
  const out: ArtifactFile[] = [];
  const seen = new Set<string>();
  for (const match of text.matchAll(FILE_MD_RE)) {
    const name = match[1]?.trim();
    const url = match[2]?.trim();
    if (!name || !url || seen.has(url)) continue;
    seen.add(url);
    const mimeType = mimeFromName(name);
    out.push({
      mimeType,
      name,
      previewable: mimeType.startsWith('image/') || mimeType === 'application/pdf' || mimeType === 'text/html',
      url,
    });
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

export function rewriteArtifactMarkdown(text: string, files: ArtifactFile[]): string {
  if (!text || !files.length) return text;
  const byName = new Map<string, string>();
  for (const file of latestDeliverables(files)) {
    byName.set(file.name, file.url);
    byName.set(basename(file.name), file.url);
  }
  const names = [...byName.keys()].sort((a, b) => b.length - a.length);
  let next = text;
  for (const name of names) {
    const url = byName.get(name);
    if (!url) continue;
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    next = next.replace(new RegExp(`]\\((?:\\./)?${escaped}\\)`, 'g'), `](${url})`);
  }
  return next;
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
