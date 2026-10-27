import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/errors";
import { makeItem } from "../../test/fixtures";
import { fakeClient, renderWithApi } from "../../test/renderWithApi";
import { PhotoSlot } from "./PhotoSlot";

const started = {
  image_id: "img-1",
  upload: { url: "https://storage.test/bucket", fields: { key: "users/u/items/item-1/img-1" } },
  expires_in: 900,
};

function setup(
  handler?: (path: string, options?: { method?: string }) => unknown,
  item = makeItem(),
) {
  const { client, request } = fakeClient(
    handler ??
      ((path) => {
        if (path.endsWith("/images")) return started;
        if (path.endsWith("/complete")) return { id: "img-1" };
        return undefined;
      }),
  );
  renderWithApi(client, { element: <PhotoSlot item={item} kind="front" /> });
  return { request };
}

function jpeg(size = 100) {
  return new File([new Uint8Array(size)], "front.jpg", { type: "image/jpeg" });
}

afterEach(() => vi.unstubAllGlobals());

describe("PhotoSlot", () => {
  it("hashes, starts, uploads to storage, then completes", async () => {
    const storage = vi.fn<typeof fetch>(() => Promise.resolve(new Response(null, { status: 204 })));
    vi.stubGlobal("fetch", storage);
    const { request } = setup();
    await userEvent.upload(screen.getByLabelText("Upload front photo"), jpeg());
    await waitFor(() =>
      expect(request.mock.calls.some(([p]) => p.endsWith("/complete"))).toBe(true),
    );
    const startCall = request.mock.calls.find(([p]) => p.endsWith("/images"))!;
    expect(startCall[1]).toMatchObject({
      method: "POST",
      body: {
        kind: "front",
        content_type: "image/jpeg",
        byte_size: 100,
        sha256: expect.stringMatching(/^[0-9a-f]{64}$/),
      },
    });
    expect(storage).toHaveBeenCalledWith(
      started.upload.url,
      expect.objectContaining({ method: "POST" }),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it.each([
    [new File(["gif"], "a.gif", { type: "image/gif" }), /JPEG, PNG, WebP, or HEIC/],
    [jpeg(15 * 1024 * 1024 + 1), /15 MB or smaller/],
  ])("rejects unsuitable files before uploading", async (file, message) => {
    const { request } = setup();
    await userEvent.upload(screen.getByLabelText("Upload front photo"), file, {
      applyAccept: false,
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(request).not.toHaveBeenCalled();
  });

  it("explains a storage rejection", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(new Response("denied", { status: 403 })));
    const { request } = setup();
    await userEvent.upload(screen.getByLabelText("Upload front photo"), jpeg());
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "File storage rejected the upload (403)",
    );
    expect(request.mock.calls.some(([p]) => p.endsWith("/complete"))).toBe(false);
  });

  it("explains a failed verification", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(new Response(null, { status: 204 })));
    setup((path) => {
      if (path.endsWith("/images")) return started;
      if (path.endsWith("/complete")) {
        throw new ApiError(422, "invalid_input", "Invalid input", {
          title: "Invalid input",
          status: 422,
          code: "invalid_input",
          detail: "file is not a valid image/jpeg",
        });
      }
      return undefined;
    });
    await userEvent.upload(screen.getByLabelText("Upload front photo"), jpeg());
    expect(await screen.findByRole("alert")).toHaveTextContent("file is not a valid image/jpeg");
  });

  it("shows, replaces, and removes an existing photo", async () => {
    const item = makeItem({
      images: {
        front: {
          id: "img-9",
          kind: "front",
          url: "https://storage.test/f.jpg",
          content_type: "image/jpeg",
          byte_size: 9,
          uploaded_at: null,
        },
        back: null,
      },
    });
    const { request } = setup(() => undefined, item);
    expect(screen.getByRole("img", { name: "Front of JJ Wetherholt" })).toHaveAttribute(
      "src",
      "https://storage.test/f.jpg",
    );
    expect(screen.getByRole("button", { name: "Replace" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("/api/v1/collection/items/item-1/images/img-9", {
        method: "DELETE",
      }),
    );
  });

  it("explains a failed removal", async () => {
    const item = makeItem({
      images: {
        front: {
          id: "img-9",
          kind: "front",
          url: "u",
          content_type: "image/jpeg",
          byte_size: 9,
          uploaded_at: null,
        },
        back: null,
      },
    });
    setup(() => {
      throw new Error("boom");
    }, item);
    await userEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/upload failed|try again/i);
  });
});
