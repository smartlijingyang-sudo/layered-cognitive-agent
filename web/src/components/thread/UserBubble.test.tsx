import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { UserBubble } from "./UserBubble";
import type { Turn } from "../../domain/conversation";

function turn(overrides: Partial<Turn> = {}): Turn {
  return {
    runId: "r1",
    traceId: "t1",
    question: "Please review this",
    mode: "board",
    status: "completed",
    answer: "",
    createdAt: Date.now(),
    ...overrides,
  };
}

describe("UserBubble", () => {
  it("renders question without attachment row when none present", () => {
    render(<UserBubble turn={turn()} />);
    expect(screen.getByText("Please review this")).toBeTruthy();
    expect(screen.queryByTestId("user-attachments")).toBeNull();
  });

  it("lists attachment chips from turn.attachments", () => {
    render(
      <UserBubble
        turn={turn({
          attachments: [
            {
              id: "a1",
              name: "spec.md",
              mimeType: "text/markdown",
              sizeBytes: 1024,
              status: "local",
            },
          ],
        })}
      />,
    );
    expect(screen.getByTestId("user-attachments")).toBeTruthy();
    expect(screen.getByText("spec.md")).toBeTruthy();
    expect(screen.getByText("1.0 KB")).toBeTruthy();
  });
});
