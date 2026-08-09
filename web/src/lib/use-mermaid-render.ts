import { useEffect, useId, useRef, useState } from "react";
import mermaid from "mermaid";

export type MermaidTheme = "dark" | "default";

let initializedTheme: MermaidTheme | null = null;

/**
 * (Re-)initialize mermaid when the requested theme differs from the current
 * one. Mermaid bakes the theme into each rendered SVG, so a theme switch must
 * re-initialize and callers must re-render.
 */
export function ensureMermaidInitialized(theme: MermaidTheme = "dark"): void {
  if (initializedTheme === theme) return;
  mermaid.initialize({
    startOnLoad: false,
    theme,
    securityLevel: "strict",
  });
  initializedTheme = theme;
}

/** Pure async render used by TraceAccordion and tests. Throws on invalid syntax. */
export async function renderMermaidSvg(
  source: string,
  renderId: string,
  theme: MermaidTheme = "dark",
): Promise<string> {
  ensureMermaidInitialized(theme);
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
 * Pass the site theme so diagrams re-render on light/dark switches.
 */
export function useMermaidRender(
  source: string | null | undefined,
  enabled = true,
  theme: MermaidTheme = "dark",
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

    void renderMermaidSvg(source, renderId, theme)
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
  }, [source, enabled, reactId, theme]);

  return state;
}

/** Test-only: allow re-init between suites if needed. */
export function __resetMermaidForTests(): void {
  initializedTheme = null;
}
