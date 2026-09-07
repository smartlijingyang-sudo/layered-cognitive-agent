// LCA-P1: Resolve the LCA gateway WebSocket URL.
//
// Resolution order (first non-empty wins):
//
//   1. `LCA_GATEWAY_WS_URL` — build-time literal injected by the
//      ``lca_runtime_agent_gateway`` patch (``apply()`` step). The
//      lobehub-spa Vite dev server does NOT expose
//      ``process.env.NEXT_PUBLIC_*`` to the browser bundle by default
//      (``vite.config.ts`` only whitelists ``VITE_*``), so the patch
//      resolves the URL once at apply time and bakes it into this file
//      as a string literal. See ``docs/notes/implemented/seam/2026-09-07-jwt-secret-injection-via-profile.md``
//      for the JWT-side seam — the same ``Vite envPrefix`` story
//      motivated this approach.
//   2. ``process.env.NEXT_PUBLIC_LCA_GATEWAY_URL`` — kept as a
//      fallback for Next.js-style hosts and for ad-hoc scripts; Vite
//      will keep this as a literal reference at build time, so it is
//      effectively a no-op in the lobehub-spa dev mode.
//   3. Tests override via ``setLcaGatewayUrl()``. A missing URL is a
//      configuration error and surfaces at first call rather than at
//      module evaluation so a server-side render with the env unset
//      does not crash SSR.

// LCA_PATCH_BEGIN: build-time URL (replaced by lca_runtime_agent_gateway.apply)
const LCA_GATEWAY_WS_URL: string = '__LCA_GATEWAY_WS_URL__:ws://lca-gateway-unset:0000__';
// LCA_PATCH_END

let cachedUrl: string | null = null;

export function getLcaGatewayUrl(): string {
  if (cachedUrl) return cachedUrl;
  // 1. build-time literal (Vite-friendly).
  if (LCA_GATEWAY_WS_URL && LCA_GATEWAY_WS_URL.length > 0) {
    cachedUrl = LCA_GATEWAY_WS_URL;
    return cachedUrl;
  }
  // 2. process.env fallback (Next.js-style / tests).
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
    'lcaGatewayUrl not configured; set NEXT_PUBLIC_LCA_GATEWAY_URL, run lca-ops to inject the build-time literal, or call setLcaGatewayUrl() in tests',
  );
}

export function setLcaGatewayUrl(url: string): void {
  cachedUrl = url;
}

export function resetLcaGatewayUrl(): void {
  cachedUrl = null;
}