export function LlmBadge({ available }: { readonly available: boolean | null }) {
  if (available === null) return null;
  return (
    <span className={`llm-badge ${available ? "ok" : "offline"}`}>
      {available ? "LLM 在线" : "离线 scripted"}
    </span>
  );
}
