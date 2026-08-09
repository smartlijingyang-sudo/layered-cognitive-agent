import { describe, expect, it } from "vitest";
import {
  filesFromToolInvoked,
  filesFromToolResultPreview,
  parseGeneratedFile,
} from "./parse-generated-file";

describe("parseGeneratedFile", () => {
  it("maps A2A / write_file shaped objects", () => {
    const file = parseGeneratedFile({
      name: "out.md",
      mimeType: "text/markdown",
      sizeBytes: 12,
      url: "/files/x",
      previewable: true,
      attachmentId: "file_x",
    });
    expect(file).toEqual({
      name: "out.md",
      mimeType: "text/markdown",
      sizeBytes: 12,
      url: "/files/x",
      attachmentId: "file_x",
      previewable: true,
      previewHtml: undefined,
    });
  });

  it("accepts snake_case mime_type", () => {
    const file = parseGeneratedFile({ name: "a.txt", mime_type: "text/plain" });
    expect(file?.mimeType).toBe("text/plain");
  });

  it("infers previewable for images when flag omitted", () => {
    const file = parseGeneratedFile({
      name: "c.png",
      mimeType: "image/png",
      url: "/files/c",
    });
    expect(file?.previewable).toBe(true);
  });
});

describe("filesFromToolResultPreview", () => {
  it("parses write_file success JSON", () => {
    const preview = JSON.stringify({
      name: "report.html",
      mimeType: "text/html",
      url: "/files/abc",
      sizeBytes: 20,
      previewable: true,
      previewHtml: "<p>hi</p>",
    });
    const files = filesFromToolResultPreview("write_file", preview, true);
    expect(files).toHaveLength(1);
    expect(files[0]?.name).toBe("report.html");
    expect(files[0]?.previewHtml).toContain("hi");
  });

  it("returns empty on failure", () => {
    expect(filesFromToolResultPreview("write_file", "{}", false)).toEqual([]);
  });

  it("parses multi-file sandbox payload (record.files)", () => {
    const preview = JSON.stringify({
      stdout: "ok\n",
      stderr: "",
      files: [
        {
          name: "chart.png",
          mimeType: "image/png",
          sizeBytes: 12,
          url: "/files/a",
          previewable: true,
          attachmentId: "file_a",
        },
        {
          name: "out.csv",
          mimeType: "text/csv",
          sizeBytes: 4,
          url: "/files/b",
          previewable: true,
          attachmentId: "file_b",
        },
      ],
    });
    const files = filesFromToolResultPreview("run_sandbox_code", preview, true);
    expect(files).toHaveLength(2);
    expect(files[0]?.name).toBe("chart.png");
    expect(files[1]?.name).toBe("out.csv");
  });
});

describe("filesFromToolInvoked", () => {
  it("uses structured files even when result_preview is invalid JSON", () => {
    const files = filesFromToolInvoked({
      toolName: "run_sandbox_code",
      resultPreview: '{"stdout": "truncated...',
      ok: true,
      files: [
        {
          name: "chart.png",
          mimeType: "image/png",
          url: "/files/a",
          previewable: true,
        },
      ],
    });
    expect(files).toHaveLength(1);
    expect(files[0]?.name).toBe("chart.png");
  });
});
