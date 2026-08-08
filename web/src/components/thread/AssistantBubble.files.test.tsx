import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { AssistantBubble } from "./AssistantBubble";
import type { Turn } from "../../domain/conversation";
import { EMPTY_TRACE_STATE } from "../../projectors";

function baseTurn(overrides: Partial<Turn> = {}): Turn {
  return {
    runId: "r1",
    traceId: "t1",
    question: "q",
    mode: "board",
    status: "completed",
    answer: "Here is your report.",
    createdAt: Date.now(),
    ...overrides,
  };
}

describe("AssistantBubble generated files", () => {
  it("mounts GeneratedFileCard when turn.files is present", () => {
    // Minimal trace shape — TraceAccordion returns null on empty events
    const turn = baseTurn({
      files: [
        {
          name: "out.html",
          mimeType: "text/html",
          url: "/files/out.html",
          previewable: true,
          previewHtml: "<p>hi</p>",
        },
      ],
    });

    render(
      <AssistantBubble
        turn={turn}
        events={[]}
        trace={EMPTY_TRACE_STATE}
        verbosity="standard"
        developerMode={false}
      />,
    );

    expect(screen.getByTestId("generated-file-card")).toBeTruthy();
    expect(screen.getByText("out.html")).toBeTruthy();
    expect(screen.getByTestId("generated-file-download")).toBeTruthy();
  });
});
