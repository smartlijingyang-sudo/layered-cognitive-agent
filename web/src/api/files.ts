/**
 * Typed file API — components must call this instead of `fetch` directly
 * (dependency-cruiser `components-no-transport` spirit; api layer owns HTTP).
 *
 * Backend endpoints do not exist yet (proposal 0003 Phase C). Callers should
 * catch {@link FileApiNotAvailableError} and keep local attachment state usable.
 */

import type { AttachmentRef } from "../domain/generated-file";

export type { AttachmentRef };

export class FileApiNotAvailableError extends Error {
  readonly status: number;

  constructor(status = 404, message = "File upload endpoint is not available yet") {
    super(message);
    this.name = "FileApiNotAvailableError";
    this.status = status;
  }
}

export async function uploadAttachment(
  conversationId: string,
  file: File,
): Promise<AttachmentRef> {
  const form = new FormData();
  form.append("file", file);

  let response: Response;
  try {
    response = await fetch(`/conversations/${encodeURIComponent(conversationId)}/attachments`, {
      method: "POST",
      body: form,
    });
  } catch (err) {
    throw new FileApiNotAvailableError(
      0,
      err instanceof Error ? err.message : "Network error during file upload",
    );
  }

  if (response.status === 404 || response.status === 501 || response.status === 405) {
    throw new FileApiNotAvailableError(response.status);
  }

  if (!response.ok) {
    const err = (await response.json().catch(() => ({}))) as {
      error?: string;
      detail?: string;
    };
    throw new Error(err.detail ?? err.error ?? `HTTP ${response.status}`);
  }

  const data = (await response.json()) as {
    attachment_id?: string;
    attachmentId?: string;
    name?: string;
    mime_type?: string;
    mimeType?: string;
    url?: string;
    size_bytes?: number;
    sizeBytes?: number;
  };

  const attachmentId = data.attachment_id ?? data.attachmentId;
  if (!attachmentId) {
    throw new Error("Upload response missing attachment id");
  }

  return {
    attachmentId,
    name: data.name ?? file.name,
    mimeType: data.mimeType ?? data.mime_type ?? (file.type || "application/octet-stream"),
    url: data.url,
    sizeBytes: data.sizeBytes ?? data.size_bytes ?? file.size,
  };
}

/** Resolve a downloadable URL for an attachment id (gateway Phase C). */
export function attachmentDownloadUrl(attachmentId: string): string {
  return `/files/${encodeURIComponent(attachmentId)}`;
}
