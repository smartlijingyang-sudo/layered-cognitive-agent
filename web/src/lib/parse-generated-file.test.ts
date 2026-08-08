import { describe, expect, it } from "vitest";
import { filesFromToolResultPreview, parseGeneratedFile } from "./parse-generated-file";

describe("parseGeneratedFile", () => {
  it("maps A2A / write_file shaped objects", () => {
    const file = parseGeneratedFile({
      name: "out.md",
      mimeType: "text/markdown",
      sizeBytes: 12,
      url: "/files/x",
      previewable: false,
    });
    expect(file).toEqual({
      name: "out.md",
      mimeType: "text/markdown",
      sizeBytes: 12,
      url: "/files/x",
      previewable: false,
      previewHtml: undefined,
    });
  });

  it("accepts snake_case mime_type", () => {
    const file = parseGeneratedFile({ name: "a.txt", mime_type: "text/plain" });
    expect(file?.mimeType).toBe("text/plain");
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
          previewable: false,
          attachmentId: "file_a",
        },
        {
          name: "out.csv",
          mimeType: "text/csv",
          sizeBytes: 4,
          url: "/files/b",
          previewable: false,
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
