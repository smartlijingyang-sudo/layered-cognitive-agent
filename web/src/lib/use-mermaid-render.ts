import { useEffect, useId, useRef, useState } from "react";
import mermaid from "mermaid";

let mermaidReady = false;

export function ensureMermaidInitialized(theme: "dark" | "default" = "dark"): void {
  if (mermaidReady) return;
  mermaid.initialize({
    startOnLoad: false,
    theme,
    securityLevel: "strict",
  });
  mermaidReady = true;
}

/** Pure async render used by TraceAccordion and tests. Throws on invalid syntax. */
export async function renderMermaidSvg(source: string, renderId: string): Promise<string> {
  ensureMermaidInitialized();
  const { svg } = await mermaid.render(renderId, source);
  return svg;
}

export type MermaidRenderState =
  | { readonly status: "idle" }
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly svg: string }
  | { readonly status: "error"; readonly source: string };

/**
 * Render a Mermaid diagram string. On failure, state is `error` so callers can
 * fall back to a readable code block instead of blanking the answer.
 */
export function useMermaidRender(
  source: string | null | undefined,
  enabled = true,
): MermaidRenderState {
  const reactId = useId().replace(/:/g, "");
  const [state, setState] = useState<MermaidRenderState>({ status: "idle" });
  const genRef = useRef(0);

  useEffect(() => {
    if (!enabled || !source?.trim()) {
      setState({ status: "idle" });
      return;
    }

    const gen = ++genRef.current;
    setState({ status: "loading" });
    const renderId = `mmd-${reactId}-${gen}`;

    void renderMermaidSvg(source, renderId)
      .then((svg) => {
        if (genRef.current === gen) {
          setState({ status: "ready", svg });
        }
      })
      .catch(() => {
        if (genRef.current === gen) {
          setState({ status: "error", source });
        }
      });
  }, [source, enabled, reactId]);

  return state;
}

/** Test-only: allow re-init between suites if needed. */
export function __resetMermaidForTests(): void {
  mermaidReady = false;
}
