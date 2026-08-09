import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { LocalAttachment } from "../../domain/generated-file";
import { PlusActionMenu } from "./PlusActionMenu";

const existing: LocalAttachment = {
  id: "att-1",
  name: "notes.txt",
  mimeType: "text/plain",
  sizeBytes: 5,
  status: "local",
};

describe("PlusActionMenu", () => {
  it("opens attachments submenu before file picker (lobehub flow)", () => {
    const onPickFiles = vi.fn();
    render(
      <PlusActionMenu
        attachments={[]}
        onPickFiles={onPickFiles}
        onRemoveAttachment={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /添加文件、技能和更多上下文/i }));
    expect(screen.getByRole("menuitem", { name: /附件/i })).toBeTruthy();
    expect(screen.queryByRole("menuitem", { name: "上传文件或图片" })).toBeNull();

    fireEvent.click(screen.getByRole("menuitem", { name: /附件/i }));
    expect(screen.getByTestId("attachments-submenu")).toBeTruthy();

    const input = screen.getByTestId("attachment-input") as HTMLInputElement;
    const file = new File(["hello"], "notes.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(onPickFiles).toHaveBeenCalled();
  });

  it("lists previously added attachments in submenu", () => {
    const onRemoveAttachment = vi.fn();
    render(
      <PlusActionMenu
        attachments={[existing]}
        onPickFiles={vi.fn()}
        onRemoveAttachment={onRemoveAttachment}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /添加文件、技能和更多上下文/i }));

    expect(screen.getByTestId("attachment-menu-item")).toBeTruthy();
    expect(screen.getByText("notes.txt")).toBeTruthy();

    fireEvent.click(screen.getByRole("menuitemcheckbox", { name: /notes\.txt/i }));
    expect(onRemoveAttachment).toHaveBeenCalledWith("att-1");
  });

  it("accepts dropped files on attachments submenu", () => {
    const onPickFiles = vi.fn();
    render(
      <PlusActionMenu
        attachments={[]}
        onPickFiles={onPickFiles}
        onRemoveAttachment={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /添加文件、技能和更多上下文/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /附件/i }));

    const row = screen.getByTestId("upload-menu-row");
    const file = new File(["x"], "drop.txt", { type: "text/plain" });
    fireEvent.drop(row, { dataTransfer: { files: [file] } });

    expect(onPickFiles).toHaveBeenCalled();
  });
});
