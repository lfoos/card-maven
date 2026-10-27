import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { StorageUploadError, uploadToStorage } from "../../api/collection";
import { ApiError } from "../../api/errors";
import type { ImageKind, Item } from "../../api/types";
import { sha256Hex } from "../../lib/sha256";
import { ACCEPTED_TYPES, MAX_BYTES } from "./photoRules";
import { collectionKeys } from "./queries";
import { useCollectionApi } from "./useSuggestions";

type Status = "idle" | "hashing" | "uploading" | "verifying" | "removing";

const STATUS_TEXT: Record<Exclude<Status, "idle">, string> = {
  hashing: "Preparing…",
  uploading: "Uploading…",
  verifying: "Checking file…",
  removing: "Removing…",
};

function describe(error: unknown): string {
  if (error instanceof ApiError) return error.detail ?? error.message;
  if (error instanceof StorageUploadError) return error.message;
  return "Upload failed. Please try again.";
}

/** One photo (front or back): shows it, and uploads, replaces, or removes it. */
export function PhotoSlot({ item, kind }: { item: Item; kind: ImageKind }) {
  const api = useCollectionApi();
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const image = item.images[kind];
  const label = kind === "front" ? "Front" : "Back";

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: collectionKeys.item(item.id) });
    void queryClient.invalidateQueries({ queryKey: collectionKeys.lists() });
  }

  async function upload(file: File) {
    setError(null);
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setError("Use a JPEG, PNG, WebP, or HEIC image.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setError("Images must be 15 MB or smaller.");
      return;
    }
    try {
      setStatus("hashing");
      const sha256 = await sha256Hex(file);
      const started = await api.startUpload(item.id, {
        kind,
        content_type: file.type,
        byte_size: file.size,
        sha256,
      });
      setStatus("uploading");
      await uploadToStorage(started.upload, file);
      setStatus("verifying");
      await api.completeUpload(item.id, started.image_id);
      await refresh();
    } catch (failure) {
      setError(describe(failure));
    } finally {
      setStatus("idle");
      if (input.current) input.current.value = "";
    }
  }

  async function remove() {
    if (!image) return;
    setError(null);
    setStatus("removing");
    try {
      await api.removeImage(item.id, image.id);
      await refresh();
    } catch (failure) {
      setError(describe(failure));
    } finally {
      setStatus("idle");
    }
  }

  const busy = status !== "idle";
  return (
    <figure className="photo">
      {image ? (
        <img src={image.url} alt={`${label} of ${item.card.name}`} className="photo__image" />
      ) : (
        <div className="photo__image photo__image--empty">No {kind} photo</div>
      )}
      <figcaption>
        <span>{label}</span>
        <span className="photo__actions">
          <input
            ref={input}
            type="file"
            accept={ACCEPTED_TYPES.join(",")}
            className="visually-hidden"
            aria-label={`Upload ${kind} photo`}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void upload(file);
            }}
            disabled={busy}
          />
          <button
            type="button"
            className="button button--quiet"
            onClick={() => input.current?.click()}
            disabled={busy}
          >
            {image ? "Replace" : "Upload"}
          </button>
          {image ? (
            <button
              type="button"
              className="button button--quiet"
              onClick={() => void remove()}
              disabled={busy}
            >
              Remove
            </button>
          ) : null}
        </span>
      </figcaption>
      {busy ? (
        <p className="muted" aria-live="polite">
          {STATUS_TEXT[status as Exclude<Status, "idle">]}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="field__error">
          {error}
        </p>
      ) : null}
    </figure>
  );
}
