import { useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Download, RotateCcw, X } from "../icons";
import { api, attributes, errorMessage, imageDescription } from "../lib";
import { ImageRecord, Library } from "../types";
import { ErrorNotice } from "./UI";
export function ImageDetail({
  image,
  library,
  close,
  reuse,
}: {
  image: ImageRecord | null;
  library: Library;
  close: () => void;
  reuse: (i: ImageRecord) => void;
}) {
  const [detail, setDetail] = useState<ImageRecord>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!image) return;
    const controller = new AbortController();
    setDetail(undefined);
    setError("");
    setLoading(true);
    api<ImageRecord>(`/api/images/${encodeURIComponent(image.id)}`, {
      signal: controller.signal,
    })
      .then((data) => {
        if (!controller.signal.aborted) {
          setDetail(data);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          setError(errorMessage(e));
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [image?.id, retry]);
  const record = detail || image;
  return (
    <Dialog.Root
      open={!!image}
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content
          className="dialog-content image-dialog"
          onCloseAutoFocus={(e) => {
            e.preventDefault();
            const origin = document.querySelector<HTMLElement>(
              "[data-detail-origin]",
            );
            const target = !origin || origin.closest('[data-state="inactive"]')
              ? document.getElementById("studio-content")
              : origin;
            target?.focus();
          }}
        >
          <Dialog.Close
            className="icon-button dialog-close"
            aria-label="Close image details"
          >
            <X size={20} />
          </Dialog.Close>
          <div className="detail-image">
            {record && (
              <img
                src={record.url}
                alt={imageDescription(record, library)}
              />
            )}
          </div>
          <div className="detail-copy">
            <span className="eyebrow">FROM YOUR COLLECTION</span>
            <Dialog.Title>Composition details</Dialog.Title>
            <Dialog.Description>
              Prompt, selected attributes, and original image metadata.
            </Dialog.Description>
            {loading && <p role="status">Loading image details…</p>}
            {error && (
              <ErrorNotice
                message={error}
                retry={() => setRetry((v) => v + 1)}
              />
            )}
            {record && (
              <>
                <dl className="metadata">
                  <div>
                    <dt>Dimensions</dt>
                    <dd>
                      {record.width} × {record.height}
                    </dd>
                  </div>
                  <div>
                    <dt>Aspect ratio</dt>
                    <dd>{record.aspect_ratio}</dd>
                  </div>
                  <div>
                    <dt>Created</dt>
                    <dd>{new Date(record.created_at).toLocaleString()}</dd>
                  </div>
                  <div>
                    <dt>Image ID</dt>
                    <dd>{record.id}</dd>
                  </div>
                  {(record.selection_sampling_seed ?? record.seed) != null && (
                    <div>
                      <dt>Selection sampling seed</dt>
                      <dd>{record.selection_sampling_seed ?? record.seed}</dd>
                    </div>
                  )}
                </dl>
                <p className="field-help">Sampling seeds describe selection plans; provider images are not deterministic. Unset attributes add no instruction and do not mean off.</p>
                <h3>Prompt</h3>
                <p className="detail-prompt">{record.prompt}</p>
                <h3>Locked attributes</h3>
                <dl className="metadata">
                  {Object.entries(record.selections || {}).map(([id, ids]) => {
                    const attr = attributes(library).find((a) => a.id === id);
                    return (
                      <div key={id}>
                        <dt>{attr?.name || id}</dt>
                        <dd>
                          {(Array.isArray(ids) ? ids : [ids])
                            .map(
                              (v) =>
                                attr?.values.find((x) => x.id === v)?.name || v,
                            )
                            .join(", ")}
                        </dd>
                      </div>
                    );
                  })}
                </dl>
                {!Object.keys(record.selections || {}).length && (
                  <p className="muted">No locked attributes recorded.</p>
                )}
                <div className="detail-actions">
                  <a
                    className="secondary"
                    href={record.url}
                    download={`atelier-${record.id}`}
                  >
                    <Download size={16} />
                    Download original
                  </a>
                  <button className="primary" onClick={() => reuse(record)}>
                    <RotateCcw size={15} />
                    Reuse selections
                  </button>
                </div>
              </>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
