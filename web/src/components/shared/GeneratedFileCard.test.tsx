import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { GeneratedFileCard, GeneratedFileList } from "./GeneratedFileCard";
import type { GeneratedFile } from "../../domain/generated-file";

const FIXTURE: GeneratedFile = {
  name: "report.html",
  mimeType: "text/html",
  sizeBytes: 2048,
  url: "https://example.com/files/report.html",
  previewable: true,
  previewHtml: "<html><body><h1>Preview</h1></body></html>",
};

describe("GeneratedFileCard", () => {
  it("renders name, mime, download and sandboxed preview from fixture", () => {
    render(<GeneratedFileCard file={FIXTURE} />);

    expect(screen.getByText("report.html")).toBeTruthy();
    expect(screen.getByText(/text\/html/)).toBeTruthy();
    expect(screen.getByText(/2\.0 KB/)).toBeTruthy();

    const download = screen.getByTestId("generated-file-download");
    expect(download.getAttribute("href")).toBe(FIXTURE.url);
    expect(download.getAttribute("download")).toBe("report.html");

    const iframe = screen.getByTestId("generated-file-preview");
    expect(iframe.tagName).toBe("IFRAME");
    expect(iframe.getAttribute("sandbox")).toBe("allow-scripts");
    expect(iframe.getAttribute("srcdoc") ?? iframe.getAttribute("srcDoc")).toContain("Preview");
  });

  it("shows no-download affordance when url missing", () => {
    render(
      <GeneratedFileCard
        file={{ name: "local.bin", mimeType: "application/octet-stream" }}
      />,
    );
    expect(screen.getByText("暂无下载地址")).toBeTruthy();
  });
});

describe("GeneratedFileList", () => {
  it("renders nothing for empty list", () => {
    const { container } = render(<GeneratedFileList files={[]} />);
    expect(container.querySelector('[data-testid="generated-file-list"]')).toBeNull();
  });

  it("renders a card per file", () => {
    render(
      <GeneratedFileList
        files={[
          FIXTURE,
          { name: "data.json", mimeType: "application/json", url: "/files/data.json" },
        ]}
      />,
    );
    expect(screen.getAllByTestId("generated-file-card")).toHaveLength(2);
  });
});
