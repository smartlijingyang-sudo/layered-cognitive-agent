import { describe, expect, it } from "vitest";
import {
  toPersistableAttachment,
  toPersistableAttachments,
  type LocalAttachment,
} from "./generated-file";

describe("toPersistableAttachment", () => {
  it("strips File handle for IDB-safe turn history", () => {
    const file = new File(["hello"], "a.txt", { type: "text/plain" });
    const att: LocalAttachment = {
      id: "1",
      name: "a.txt",
      mimeType: "text/plain",
      sizeBytes: 5,
      status: "local",
      file,
    };
    const persisted = toPersistableAttachment(att);
    expect(persisted.file).toBeUndefined();
    expect(persisted.name).toBe("a.txt");
    expect(persisted.mimeType).toBe("text/plain");
    expect(persisted.sizeBytes).toBe(5);
  });

  it("normalizes uploading status to local when persisting mid-flight", () => {
    const att: LocalAttachment = {
      id: "2",
      name: "b.pdf",
      mimeType: "application/pdf",
      sizeBytes: 10,
      status: "uploading",
    };
    expect(toPersistableAttachment(att).status).toBe("local");
  });

  it("returns undefined for empty attachment lists", () => {
    expect(toPersistableAttachments(undefined)).toBeUndefined();
    expect(toPersistableAttachments([])).toBeUndefined();
  });
});
