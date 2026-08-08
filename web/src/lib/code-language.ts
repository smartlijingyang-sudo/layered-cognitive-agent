/** Parse fenced-code language from react-markdown `className` (e.g. `language-python`). */

const LANGUAGE_CLASS_RE = /language-([\w#+-]+)/i;

export function parseCodeLanguage(className: string | undefined | null): string | undefined {
  if (!className) return undefined;
  const match = LANGUAGE_CLASS_RE.exec(className);
  return match?.[1]?.toLowerCase();
}

export function isMermaidLanguage(language: string | undefined | null): boolean {
  return language === "mermaid";
}
