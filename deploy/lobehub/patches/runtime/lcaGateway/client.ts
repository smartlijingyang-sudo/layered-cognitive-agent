// LCA-P1: Resolve the LCA gateway WebSocket URL.
//
// In production the URL is injected by the server-rendered config
// store (NEXT_PUBLIC_LCA_GATEWAY_URL). Tests override via
// setLcaGatewayUrl(). A missing URL is a configuration error — we
// surface it at first call rather than at module evaluation so a
// server-side render with the env unset does not crash SSR.

let cachedUrl: string | null = null;

export function getLcaGatewayUrl(): string {
  if (cachedUrl) return cachedUrl;
  const envUrl =
    typeof process !== 'undefined'
      ? (process as { env?: Record<string, string | undefined> }).env
          ?.NEXT_PUBLIC_LCA_GATEWAY_URL
      : undefined;
  if (envUrl && envUrl.length > 0) {
    cachedUrl = envUrl;
    return cachedUrl;
  }
  throw new Error(
    'lcaGatewayUrl not configured; set NEXT_PUBLIC_LCA_GATEWAY_URL or call setLcaGatewayUrl() in tests',
  );
}

export function setLcaGatewayUrl(url: string): void {
  cachedUrl = url;
}

export function resetLcaGatewayUrl(): void {
  cachedUrl = null;
}