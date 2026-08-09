import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { AssistantTurnView } from "../turn/AssistantTurnView";
import type { Turn } from "../../domain/conversation";
import { EMPTY_TURN_TIMELINE } from "../../projectors";

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

describe("AssistantTurnView generated files", () => {
  it("mounts GeneratedFileCard when turn.files is present", () => {
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
      <AssistantTurnView
        turn={turn}
        timeline={{
          ...EMPTY_TURN_TIMELINE,
          finalAnswer: turn.answer,
          status: "completed",
          files: turn.files ?? [],
        }}
      />,
    );

    expect(screen.getByText("out.html")).toBeInTheDocument();
  });
});
