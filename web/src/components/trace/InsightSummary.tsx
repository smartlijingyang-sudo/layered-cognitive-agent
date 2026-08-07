import type { RunInsight } from "../../contracts";

export function InsightSummary({ insights }: { readonly insights: readonly RunInsight[] }) {
  if (insights.length === 0) return null;
  return (
    <section className="insight-summary">
      <h3>协作摘要</h3>
      <ul>
        {insights.map((insight, index) => (
          <li key={`${insight.kind}-${index}`}>
            <strong>{insight.kind}</strong>
            <span>{insight.summary || insight.detail}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
