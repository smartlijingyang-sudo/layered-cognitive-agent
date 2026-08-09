import { describe, expect, it } from "vitest";
import { extractUserFacingAnswer } from "./extract-decision-text";
import { mergedStepChannelText, stepChannelKey } from "./step-text-buffer";

describe("mergedStepChannelText", () => {
  it("joins decision prefix with answer-channel tail for respond JSON", () => {
    const buffers = new Map<string, string>([
      [stepChannelKey("r1", 1, "decision"), '{"action_type":"respond","response_text":"'],
      [stepChannelKey("r1", 1, "answer"), '你好世界"}'],
    ]);
    const merged = mergedStepChannelText(buffers, "r1", 1);
    expect(extractUserFacingAnswer(merged)).toBe("你好世界");
  });
});
