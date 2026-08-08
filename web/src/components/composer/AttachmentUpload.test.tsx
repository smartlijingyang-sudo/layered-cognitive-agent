import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AttachmentUpload } from "./AttachmentUpload";
import type { LocalAttachment } from "../../domain/generated-file";
import * as filesApi from "../../api/files";

describe("AttachmentUpload", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("accepts a File via input and lists it", async () => {
    const onChange = vi.fn();
    render(
      <AttachmentUpload attachments={[]} onChange={onChange} />,
    );

    const input = screen.getByTestId("attachment-input") as HTMLInputElement;
    const file = new File(["hello"], "notes.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(onChange).toHaveBeenCalled();
    });
    const next = onChange.mock.calls.at(-1)?.[0] as LocalAttachment[];
    expect(next).toHaveLength(1);
    expect(next[0]?.name).toBe("notes.txt");
    expect(next[0]?.mimeType).toBe("text/plain");
    expect(next[0]?.status).toBe("local");
  });

  it("removes an attachment when remove is clicked", () => {
    const existing: LocalAttachment = {
      id: "att-1",
      name: "notes.txt",
      mimeType: "text/plain",
      sizeBytes: 5,
      status: "local",
    };
    const onChange = vi.fn();
    render(
      <AttachmentUpload attachments={[existing]} onChange={onChange} />,
    );

    expect(screen.getByTestId("attachment-chip")).toBeTruthy();
    fireEvent.click(screen.getByTestId("attachment-remove"));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("routes upload through api/files and degrades cleanly on 404", async () => {
    const uploadSpy = vi
      .spyOn(filesApi, "uploadAttachment")
      .mockRejectedValue(new filesApi.FileApiNotAvailableError(404));

    const onChange = vi.fn();
    const { rerender } = render(
      <AttachmentUpload
        attachments={[]}
        onChange={onChange}
        conversationId="conv-1"
        autoUpload
      />,
    );

    const input = screen.getByTestId("attachment-input") as HTMLInputElement;
    const file = new File(["x"], "a.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(uploadSpy).toHaveBeenCalledWith("conv-1", expect.any(File));
    });

    // Last onChange should keep the attachment usable with error status
    await waitFor(() => {
      const last = onChange.mock.calls.at(-1)?.[0] as LocalAttachment[];
      expect(last?.[0]?.status).toBe("error");
      expect(last?.[0]?.error).toMatch(/后端尚未开放|not available/i);
    });

    // Re-render with errored attachment — UI still shows chip (usable)
    const last = onChange.mock.calls.at(-1)?.[0] as LocalAttachment[];
    rerender(
      <AttachmentUpload
        attachments={last}
        onChange={onChange}
        conversationId="conv-1"
        autoUpload
      />,
    );
    expect(screen.getByTestId("attachment-chip")).toBeTruthy();
    expect(screen.getByText("a.txt")).toBeTruthy();
  });
});
