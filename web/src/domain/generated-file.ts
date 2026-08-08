/**
 * Generated file product shape — aligned with A2A artifact file parts
 * (`name` / `mimeType` / bytes-or-URI), per ADR-0043 decision II.
 */

export interface GeneratedFile {
  readonly name: string;
  readonly mimeType: string;
  readonly sizeBytes?: number;
  /** Backend-downloadable URI when available. */
  readonly url?: string;
  /** When true, UI may show a sandboxed HTML preview. */
  readonly previewable?: boolean;
  /**
   * Optional inline HTML for `iframe srcDoc` (fixture / mock path).
   * Prefer over fetching when content is already in memory.
   */
  readonly previewHtml?: string;
}

export interface AttachmentRef {
  readonly attachmentId: string;
  readonly name: string;
  readonly mimeType: string;
  readonly url?: string;
  readonly sizeBytes?: number;
}

/** Local composer attachment before/without backend upload. */
export interface LocalAttachment {
  readonly id: string;
  readonly name: string;
  readonly mimeType: string;
  readonly sizeBytes: number;
  readonly status: "local" | "uploading" | "uploaded" | "error";
  readonly error?: string;
  readonly ref?: AttachmentRef;
  /** In-memory File for upload; may be absent after restore. */
  readonly file?: File;
}

/**
 * Strip non-essential runtime handles (`File`) before IDB / turn history.
 * Keeps name/mime/size/status so the thread can rehydrate chips after reload.
 */
export function toPersistableAttachment(att: LocalAttachment): LocalAttachment {
  return {
    id: att.id,
    name: att.name,
    mimeType: att.mimeType,
    sizeBytes: att.sizeBytes,
    status: att.status === "uploading" ? "local" : att.status,
    error: att.error,
    ref: att.ref,
  };
}

export function toPersistableAttachments(
  attachments: readonly LocalAttachment[] | undefined,
): readonly LocalAttachment[] | undefined {
  if (!attachments?.length) return undefined;
  return attachments.map(toPersistableAttachment);
}
