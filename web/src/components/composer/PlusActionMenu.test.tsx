import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PlusActionMenu } from "./PlusActionMenu";

describe("PlusActionMenu", () => {
  it("opens menu and picks files via lobehub upload row", () => {
    const onPickFiles = vi.fn();
    render(<PlusActionMenu attachmentCount={0} onPickFiles={onPickFiles} />);

    fireEvent.click(screen.getByRole("button", { name: /添加文件、技能和更多上下文/i }));
    expect(screen.getByRole("menuitem", { name: "上传文件或图片" })).toBeTruthy();

    const input = screen.getByTestId("attachment-input") as HTMLInputElement;
    const file = new File(["hello"], "notes.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(onPickFiles).toHaveBeenCalled();
  });
});
