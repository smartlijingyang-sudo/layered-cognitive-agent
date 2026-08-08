import { describe, expect, it } from "vitest";
import { fileIconKind, formatByteSize } from "./file-mime-icon";

describe("fileIconKind", () => {
  it("maps common mime types", () => {
    expect(fileIconKind("image/png")).toBe("image");
    expect(fileIconKind("application/pdf")).toBe("pdf");
    expect(fileIconKind("text/html")).toBe("html");
    expect(fileIconKind("application/json")).toBe("code");
    expect(fileIconKind("application/zip")).toBe("archive");
  });

  it("falls back to extension when mime is generic", () => {
    expect(fileIconKind("application/octet-stream", "report.xlsx")).toBe("table");
    expect(fileIconKind("application/octet-stream", "note.md")).toBe("text");
  });

  it("defaults to file", () => {
    expect(fileIconKind("application/x-unknown")).toBe("file");
  });
});

describe("formatByteSize", () => {
  it("formats bytes", () => {
    expect(formatByteSize(500)).toBe("500 B");
    expect(formatByteSize(2048)).toBe("2.0 KB");
    expect(formatByteSize(2 * 1024 * 1024)).toBe("2.0 MB");
    expect(formatByteSize(undefined)).toBeUndefined();
  });
});
