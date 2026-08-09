import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FileUp } from "lucide-react";
import { LobeIcon } from "../../lib/icons";
import { UploadMenuRow } from "./UploadMenuRow";

describe("UploadMenuRow", () => {
  it("opens file picker via label click and highlights on drag over", () => {
    const onFiles = vi.fn();
    render(
      <UploadMenuRow
        onFiles={onFiles}
        icon={<LobeIcon icon={FileUp} size={20} />}
        label="上传文件或图片"
      />,
    );

    const row = screen.getByTestId("upload-menu-row");
    const host = row.parentElement!;
    fireEvent.dragEnter(host, { dataTransfer: { dropEffect: "copy" } });
    expect(host.className).toMatch(/ring-/);

    const file = new File(["x"], "a.txt", { type: "text/plain" });
    fireEvent.drop(host, { dataTransfer: { files: [file] } });
    expect(onFiles).toHaveBeenCalled();
  });
});
