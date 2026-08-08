import { afterEach, describe, expect, it, vi } from "vitest";
import { FileApiNotAvailableError, uploadAttachment } from "./files";

describe("uploadAttachment", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("returns AttachmentRef on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          attachment_id: "att-99",
          name: "doc.pdf",
          mime_type: "application/pdf",
          url: "/files/att-99",
          size_bytes: 12,
        }),
      }),
    );

    const file = new File(["%PDF"], "doc.pdf", { type: "application/pdf" });
    const ref = await uploadAttachment("c1", file);
    expect(ref.attachmentId).toBe("att-99");
    expect(ref.name).toBe("doc.pdf");
    expect(ref.mimeType).toBe("application/pdf");
    expect(ref.url).toBe("/files/att-99");
    expect(fetch).toHaveBeenCalledWith(
      "/conversations/c1/attachments",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("throws FileApiNotAvailableError on 404", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({}),
      }),
    );

    const file = new File(["x"], "a.txt", { type: "text/plain" });
    await expect(uploadAttachment("c1", file)).rejects.toBeInstanceOf(
      FileApiNotAvailableError,
    );
  });
});
