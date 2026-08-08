/**
 * Lazy Shiki highlighter for fenced code blocks.
 * Returns HTML string on success, or `null` so callers can fall back to plain `<pre><code>`.
 */

const SUPPORTED_LANGS = [
  "typescript",
  "javascript",
  "tsx",
  "jsx",
  "python",
  "json",
  "bash",
  "shell",
  "sh",
  "css",
  "html",
  "markdown",
  "md",
  "yaml",
  "yml",
  "sql",
  "go",
  "rust",
  "java",
  "c",
  "cpp",
  "text",
  "plaintext",
] as const;

type SupportedLang = (typeof SUPPORTED_LANGS)[number];

type Highlighter = {
  codeToHtml: (
    code: string,
    options: { lang: string; theme: string },
  ) => string;
  loadLanguage: (lang: string) => Promise<void>;
  getLoadedLanguages: () => string[];
};

let highlighterPromise: Promise<Highlighter> | null = null;

function resolveLang(language: string | undefined): SupportedLang {
  if (!language) return "text";
  const lower = language.toLowerCase();
  if ((SUPPORTED_LANGS as readonly string[]).includes(lower)) {
    return lower as SupportedLang;
  }
  // Common aliases
  if (lower === "ts") return "typescript";
  if (lower === "js") return "javascript";
  if (lower === "py") return "python";
  return "text";
}

async function getHighlighter(): Promise<Highlighter> {
  if (!highlighterPromise) {
    highlighterPromise = import("shiki").then(async (mod) => {
      const highlighter = await mod.createHighlighter({
        themes: ["github-dark"],
        langs: [...SUPPORTED_LANGS],
      });
      return highlighter as Highlighter;
    });
  }
  return highlighterPromise;
}

/**
 * Highlight `code` for `language`. Returns highlighted HTML, or `null` on any failure.
 * Never throws — callers must keep the plain code path.
 */
export async function highlightCode(
  code: string,
  language: string | undefined,
): Promise<string | null> {
  try {
    const highlighter = await getHighlighter();
    const lang = resolveLang(language);
    const loaded = highlighter.getLoadedLanguages?.() ?? [];
    if (loaded.length > 0 && !loaded.includes(lang) && lang !== "text") {
      try {
        await highlighter.loadLanguage(lang);
      } catch {
        // fall through to text
      }
    }
    return highlighter.codeToHtml(code, { lang, theme: "github-dark" });
  } catch {
    return null;
  }
}

/** Test helper: force next getHighlighter to re-import (and optionally fail). */
export function __resetHighlighterForTests(): void {
  highlighterPromise = null;
}
