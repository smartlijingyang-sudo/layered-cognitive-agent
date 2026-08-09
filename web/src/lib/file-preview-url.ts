/**
 * Build URLs for in-app file preview vs download.
 * Gateway serves inline when `preview=1` (or image/* always inline).
 */

export function filePreviewUrl(url: string | undefined): string | undefined {
  if (!url?.trim()) return undefined;
  try {
    const base =
      typeof window !== "undefined" ? window.location.origin : "http://localhost";
    const u = new URL(url, base);
    u.searchParams.set("preview", "1");
    // Prefer path+search when same-origin relative input
    if (url.startsWith("/")) {
      return `${u.pathname}${u.search}`;
    }
    return u.toString();
  } catch {
    const sep = url.includes("?") ? "&" : "?";
    return `${url}${sep}preview=1`;
  }
}

export function fileDownloadUrl(url: string | undefined): string | undefined {
  return url?.trim() || undefined;
}
