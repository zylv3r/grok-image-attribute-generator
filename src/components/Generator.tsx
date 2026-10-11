import { useEffect, useRef, useState } from "react";
import {
  ArrowUpRight,
  ChevronDown,
  Eye,
  LockKeyhole,
  Play,
  RefreshCw,
  Shuffle,
  X,
} from "../icons";
import {
  api,
  ApiError,
  attributes,
  errorMessage,
  writeStorage,
  readStorage,
  setAttribute,
  generationPayload,
  combinationLabel,
} from "../lib";
import {
  Draft,
  ImageRecord,
  Job,
  Library,
  Mode,
  Preview,
  ratios,
} from "../types";
import { ErrorNotice, Picker, Thumb } from "./UI";
const terminal = (job: Job) =>
  ["completed", "partial", "failed"].includes(job.status);
export function Generator({
  library,
  draft,
  change,
  onImage,
  onComplete,
  onEditAttribute,
}: {
  library: Library;
  draft: Draft;
  change: (d: Draft) => void;
  onImage: (i: ImageRecord) => void;
  onComplete: () => void;
  onEditAttribute: (id: string) => void;
}) {
  const [preview, setPreview] = useState<{
    signature: string;
    data: Preview;
  }>();
  const [previewing, setPreviewing] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [job, setJob] = useState<Job>();
  const [jobId, setJobId] = useState(() => {
    const v = readStorage("atelier.job.v1");
    return typeof v === "string" ? v : "";
  });
  const [pollError, setPollError] = useState("");
  const [pollRetry, setPollRetry] = useState(0);
  const [seedText, setSeedText] = useState(draft.seed?.toString() || "");
  const [modeNotice, setModeNotice] = useState("");
  const requestLock = useRef(false),
    previewLock = useRef(false);
  const previewAbort = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const completeCallback = useRef(onComplete);
  completeCallback.current = onComplete;
  const signature = JSON.stringify(generationPayload(draft));
  const visiblePreview =
    preview?.signature === signature ? preview.data : undefined;
  const busy = submitting || (!!jobId && (!job || !terminal(job)));
  const seedInvalid =
    seedText !== "" &&
    (!/^\d+$/.test(seedText) || !Number.isSafeInteger(Number(seedText)));
  useEffect(() => {
    setSeedText(draft.seed?.toString() || "");
  }, [draft.seed]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      previewAbort.current?.abort();
    };
  }, []);
  useEffect(() => {
    previewAbort.current?.abort();
    setPreviewing(false);
    previewLock.current = false;
    setError("");
  }, [signature]);
  useEffect(() => {
    if (!jobId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setPollError("");
    async function poll() {
      try {
        const next = await api<Job>(`/api/jobs/${encodeURIComponent(jobId)}`, {
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        setJob(next);
        if (terminal(next)) {
          writeStorage("atelier.job.v1", null);
          completeCallback.current();
        } else timer = setTimeout(poll, 1500);
      } catch (e) {
        if (controller.signal.aborted) return;
        if (e instanceof ApiError && e.status === 404) {
          writeStorage("atelier.job.v1", null);
          setJobId("");
          setJob(undefined);
          setError(
            "The saved job could not be found. You can submit a new generation.",
          );
        } else setPollError(errorMessage(e));
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [jobId, pollRetry]);
  async function getPreview() {
    if (previewLock.current || seedInvalid) return;
    previewLock.current = true;
    setPreviewing(true);
    setError("");
    const controller = new AbortController();
    previewAbort.current = controller;
    try {
      const data = await api<Preview>("/api/preview", {
        method: "POST",
        body: signature,
        signal: controller.signal,
      });
      if (!controller.signal.aborted) setPreview({ signature, data });
    } catch (e) {
      if (!controller.signal.aborted) setError(errorMessage(e));
    } finally {
      if (!controller.signal.aborted) {
        setPreviewing(false);
        previewLock.current = false;
      }
    }
  }
  async function generate() {
    if (requestLock.current || busy || seedInvalid) return;
    requestLock.current = true;
    setSubmitting(true);
    setError("");
    try {
      const result = await api<{ id: string }>("/api/jobs", {
        method: "POST",
        body: signature,
      });
      writeStorage("atelier.job.v1", result.id);
      if (mounted.current) {
        setJob(undefined);
        setJobId(result.id);
      }
    } catch (e) {
      if (mounted.current) setError(errorMessage(e));
    } finally {
      requestLock.current = false;
      if (mounted.current) setSubmitting(false);
    }
  }
  function switchMode(mode: Mode) {
    let next = { ...draft };
    let removed = 0;
    const converted = Object.keys(draft.whitelist).length;
    if (mode !== "variations") {
      for (const attr of attributes(library))
        if (next.whitelist[attr.id]) {
          if (attr.type !== "multi") removed += Math.max(0, next.whitelist[attr.id].length - 1);
          next = setAttribute(
            next,
            attr,
            "selections",
            next.whitelist[attr.id],
          );
        }
      next = { ...next, attributeModes: Object.fromEntries(Object.keys(next.attributeModes || {}).map((id) => [id, "selections" as const])) };
    }
    setModeNotice(converted && mode !== "variations" ? `${converted} varying ${converted === 1 ? "attribute moved" : "attributes moved"} to Lock. ${removed ? `${removed} allowed ${removed === 1 ? "value removed" : "values removed"}; the first choice in each exclusive attribute was kept.` : "All choices retained."}` : `Generation mode: ${mode}.`);
    change({
      ...next,
      mode,
      n: mode === "single" ? 1 : draft.n === 1 ? 4 : draft.n,
    });
  }
  function remove(id: string) {
    const selections = { ...draft.selections },
      whitelist = { ...draft.whitelist };
    delete selections[id];
    delete whitelist[id];
    setModeNotice(`${attributes(library).find((attr) => attr.id === id)?.name || id} cleared. It adds no instruction; unset does not mean off.`);
    change({ ...draft, selections, whitelist });
  }
  const attrs = attributes(library);
  const count = Object.keys(draft.selections).length;
  return (
    <aside id="composition" tabIndex={-1} className="generator" aria-label="Generation settings">
      <div className="generator-title">
        <span className="eyebrow">YOUR COMPOSITION</span>
        <h2>Make it yours.</h2>
        <p>Lock a direction. Leave room for discovery.</p>
      </div>
      <div className="selection-summary">
        <h3>
          <LockKeyhole size={14} />
          Locked attributes <span>{count}</span>
        </h3>
        {count ? (
          <div className="locked-chips">
            {Object.entries(draft.selections).map(([id, ids]) => (
              <button
                className="locked-chip"
                key={id}
                onClick={() => remove(id)}
                aria-label={`Remove ${attrs.find((a) => a.id === id)?.name}`}
              >
                <span>
                  <small>{attrs.find((a) => a.id === id)?.name}</small>
                  {ids
                    .map(
                      (v) =>
                        attrs
                          .find((a) => a.id === id)
                          ?.values.find((x) => x.id === v)?.name,
                    )
                    .join(", ")}
                </span>
                <X size={13} />
              </button>
            ))}
          </div>
        ) : (
          <p className="muted">
            Choose values in the library to shape your image.
          </p>
        )}
        {Object.keys(draft.whitelist).length > 0 && (
          <div className="variation-summary">
            <h3>
              <Shuffle size={14} />
              Allowed variations
            </h3>
            {Object.entries(draft.whitelist).map(([id, ids]) => (
              <button
                className="locked-chip"
                key={id}
                onClick={() => remove(id)}
                aria-label={`Remove variations ${attrs.find((a) => a.id === id)?.name}`}
              >
                <span>
                  <small>{attrs.find((a) => a.id === id)?.name}</small>
                  {ids
                    .map(
                      (v) =>
                        attrs
                          .find((a) => a.id === id)
                          ?.values.find((x) => x.id === v)?.name,
                    )
                    .join(", ")}
                </span>
                <X size={13} />
              </button>
            ))}
          </div>
        )}
        {(count > 0 || Object.keys(draft.whitelist).length > 0) && <nav className="composition-navigation" aria-label="Edit selected attributes">{Object.keys({ ...draft.selections, ...draft.whitelist }).map((id) => <button key={id} className="text-button" onClick={() => onEditAttribute(id)}>Find {attrs.find((a) => a.id === id)?.name} in library</button>)}</nav>}
      </div>
      <div className="settings">
        <label className="field-label">Generation mode</label>
        <Picker
          label="Generation mode"
          value={draft.mode}
          onChange={(v) => switchMode(v as Mode)}
          options={[
            { value: "single", label: "Single · one composition" },
            { value: "repeat", label: "Repeat · same direction" },
            {
              value: "variations",
              label: "Variations · explore allowed values",
            },
          ]}
        />
        <p className="field-help">
          {draft.mode === "variations"
            ? "Plans vary only the whitelisted values; locks stay fixed."
            : draft.mode === "repeat"
              ? "Repeat the same locked composition."
              : "Generate one image from your locked composition."}
        </p>
        <p className="field-help">
          Choosing Single or Repeat moves allowed values into locks (one for
          exclusive attributes).
        </p>
        {modeNotice && <p className="field-help" role="status">{modeNotice}</p>}
        <div className="field-pair">
          <div>
            <label className="field-label" htmlFor="image-count">
              Images
            </label>
            <input
              id="image-count"
              type="number"
              min={1}
              max={24}
              disabled={draft.mode === "single"}
              value={draft.n}
              onChange={(e) =>
                change({
                  ...draft,
                  n: Math.min(
                    24,
                    Math.max(1, Math.trunc(Number(e.target.value)) || 1),
                  ),
                })
              }
            />
          </div>
          <div>
            <label className="field-label">Aspect ratio</label>
            <Picker
              label="Aspect ratio"
              value={draft.aspect_ratio}
              onChange={(aspect_ratio) => change({ ...draft, aspect_ratio })}
              options={ratios.map((value) => ({ value, label: value }))}
            />
          </div>
        </div>
        <label className="field-label" htmlFor="extra-prompt">
          Your creative note <span>optional</span>
        </label>
        <textarea
          id="extra-prompt"
          rows={3}
          maxLength={10000}
          placeholder="Soft afternoon light, a quiet cinematic mood…"
          value={draft.extra_prompt}
          onChange={(e) => change({ ...draft, extra_prompt: e.target.value })}
        />
        <label className="field-label" htmlFor="seed">
          Selection sampling seed <span>optional</span>
        </label>
        <input
          id="seed"
          type="text"
          inputMode="numeric"
          placeholder="Random"
          value={seedText}
          aria-invalid={seedInvalid}
          aria-describedby="seed-help"
          onChange={(e) => {
            const value = e.target.value;
            setSeedText(value);
            if (
              value === "" ||
              (/^\d+$/.test(value) && Number.isSafeInteger(Number(value)))
            )
              change({
                ...draft,
                seed: value === "" ? undefined : Number(value),
              });
          }}
        />
        <p id="seed-help" className="field-help">Reproduces selection sampling and plan order. It does not make provider images deterministic.</p>
        {seedInvalid && (
          <p className="validation" role="alert">
            Enter a nonnegative whole number within the safe integer range.
          </p>
        )}
      </div>
      <button
        className="secondary wide"
        onClick={getPreview}
        disabled={previewing || seedInvalid}
      >
        <Eye size={16} />
        {previewing ? "Preparing preview…" : "Preview prompt & plans"}
      </button>
      {visiblePreview && (
        <div className="preview-panel" aria-label="Prompt preview">
          <div className="preview-meta">
            <strong>
              {combinationLabel(visiblePreview)}
            </strong>
            <span>
              {visiblePreview.plans.length}{" "}
              {visiblePreview.plans.length === 1 ? "plan" : "plans"}
            </span>
          </div>
          {visiblePreview.combination_count_exact === false && <p className="field-help">Approximate count: bounded search found this many compatible combinations. More may exist; sampling is not guaranteed uniform.{visiblePreview.combination_count_metadata && ` Before compatibility filtering, the upper bound is ${visiblePreview.combination_count_metadata.unrestricted_product_count.toLocaleString()}.`}</p>}
          {draft.mode === "repeat" && draft.n > 1 && <p className="field-help">{draft.n} images repeat the same selection plan.</p>}
          {visiblePreview.plans.map((plan, i) => (
            <details key={i} open={i === 0}>
              <summary>
                Plan {i + 1}
                <ChevronDown size={14} />
              </summary>
              <p>{plan.prompt}</p>
              <dl>
                {Object.entries(plan.selections).map(([id, ids]) => (
                  <div key={id}>
                    <dt>{attrs.find((a) => a.id === id)?.name || id}</dt>
                    <dd>
                      {(Array.isArray(ids) ? ids : [ids])
                        .map(
                          (v) =>
                            attrs
                              .find((a) => a.id === id)
                              ?.values.find((x) => x.id === v)?.name || v,
                        )
                        .join(", ")}
                    </dd>
                  </div>
                ))}
              </dl>
            </details>
          ))}
        </div>
      )}
      {error && <ErrorNotice message={error} />}
      <button
        className="primary wide generate-button"
        onClick={generate}
        disabled={busy || seedInvalid}
      >
        <Play size={16} fill="currentColor" />
        {busy
          ? submitting
            ? "Submitting…"
            : "Generation in progress"
          : `Generate ${draft.n} image${draft.n === 1 ? "" : "s"}`}
        <ArrowUpRight size={17} />
      </button>
      <p className="generation-note">
        {draft.n} billed image {draft.n === 1 ? "call" : "calls"} to the connected image service. Preview makes no image calls.
      </p>
      {jobId && (
        <section
          className="job-status"
          aria-label="Generation progress"
          aria-live="polite"
        >
          <div className="preview-meta">
            <strong>
              {job
                ? job.status === "partial"
                  ? "Partially completed"
                  : job.status[0].toUpperCase() + job.status.slice(1)
                : "Checking job…"}
            </strong>
            <span>{job ? `${job.completed} / ${job.total}` : ""}</span>
          </div>
          {job && (
            <>
              <progress
                max={job.total || 1}
                value={job.completed + job.failed}
                aria-label="Job progress"
              />
              <p>
                {job.completed} completed · {job.failed} failed · {job.total}{" "}
                total
              </p>
              {job.errors?.map((e, i) => (
                <div className="job-error" key={i}>
                  {errorMessage(e)}
                </div>
              ))}
              <div className="job-results">
                {job.results?.map((i) => (
                  <button
                    key={i.id}
                    onClick={() => onImage(i)}
                    aria-label={`Open generated image ${i.id}`}
                  >
                    <Thumb url={i.thumbnail_url || i.url} name="Result" />
                  </button>
                ))}
              </div>
            </>
          )}
          {pollError && (
            <ErrorNotice
              message={`Progress unavailable: ${pollError}`}
              retry={() => setPollRetry((v) => v + 1)}
            />
          )}
          {pollError && (
            <p className="muted">
              Your job may still be running. Retry checks its status without
              submitting again.
            </p>
          )}
          {job && terminal(job) && (
            <button
              className="text-button"
              onClick={() => {
                setJobId("");
                setJob(undefined);
              }}
            >
              <RefreshCw size={13} />
              Dismiss results
            </button>
          )}
        </section>
      )}
    </aside>
  );
}
