import { useEffect, useState } from "react";

export type SiteTheme = "light" | "dark";

/** The single source of truth is `documentElement[data-theme]` (set by App). */
export function readSiteTheme(): SiteTheme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

/**
 * Reactive site theme. Re-renders subscribers when the theme toggles so
 * canvas-style renderers (Mermaid) can re-emit theme-matched output.
 * Shiki needs no re-render: its dual-theme output is CSS-switched.
 */
export function useSiteTheme(): SiteTheme {
  const [theme, setTheme] = useState<SiteTheme>(readSiteTheme);

  useEffect(() => {
    setTheme(readSiteTheme());
    const observer = new MutationObserver(() => {
      setTheme((prev) => {
        const next = readSiteTheme();
        return next === prev ? prev : next;
      });
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  return theme;
}
