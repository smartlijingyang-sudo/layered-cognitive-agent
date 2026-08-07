import type { RunInsight } from "../../contracts";
import { mutedText } from "../../lib/ui";

export function InsightSummary({ insights }: { readonly insights: readonly RunInsight[] }) {
  if (insights.length === 0) return null;
  return (
    <section className="mb-2">
      <h3 className="m-0 text-sm font-semibold">协作摘要</h3>
      <ul className="mt-2 flex list-none flex-col gap-2 p-0">
        {insights.map((insight, index) => (
          <li key={`${insight.kind}-${index}`} className="flex flex-col gap-0.5 text-sm">
            <strong>{insight.kind}</strong>
            <span className={mutedText}>{insight.summary || insight.detail}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
