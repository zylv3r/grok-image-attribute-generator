import { useEffect, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "../icons";
import { api, ApiError, attributes, cleanDraft, errorMessage, presetApplication } from "../lib";
import type { Draft, DraftResolution, Library } from "../types";
import "./migration-review.css";

export type MigrationSource = { name: string; draft: Record<string, unknown>; schemaVersion?: number };
export type MigrationResult = { draft: Draft; changes: unknown[]; unresolved: unknown[]; legacy: boolean };

// Resolution never changes the archive. Only the explicit review action changes the editor.
export async function resolveMigration(source: MigrationSource, library: Library, signal?: AbortSignal): Promise<MigrationResult> {
  try {
    const result = await api<DraftResolution>("/api/catalog/resolve", {
      method: "POST", body: JSON.stringify({ draft: source.draft }), signal,
    });
    if (!result || !result.draft || typeof result.draft !== "object" || Array.isArray(result.draft) || !Array.isArray(result.changes) || !Array.isArray(result.unresolved)) {
      throw Error("The server returned an unreadable catalog resolution. The archive has been kept.");
    }
    const draft = cleanDraft(result.draft, library);
    // Surface every additional normalization, rather than silently discarding a future field.
    const local = presetApplication(result.draft, library, 1);
    return { draft, changes: result.changes, unresolved: [...result.unresolved, ...local.unresolved], legacy: false };
  } catch (error) {
    // Custom/v1 installations have no v2 resolver. Other failures must block application.
    if (!(error instanceof ApiError) || error.status !== 404) throw error;
    const result = presetApplication(source.draft, library, source.schemaVersion);
    return { ...result, changes: [], legacy: true };
  }
}

function detail(value: unknown): string {
  if (value === null || value === undefined) return "Unset";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(detail).join(", ") || "None";
  if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${key.replaceAll("_", " ")}: ${detail(item)}`).join(" · ");
  return String(value);
}
function ResolutionList({ items, empty }: { items: unknown[]; empty: string }) {
  return items.length ? <ul>{items.map((item, index) => <li key={index}>{detail(item)}</li>)}</ul> : <p className="muted">{empty}</p>;
}
function AppliedControls({ draft, library }: { draft: Draft; library: Library }) {
  const attrs = attributes(library);
  const rows = (["selections", "whitelist"] as const).flatMap(field => Object.entries(draft[field]).map(([id, ids]) => {
    const attr = attrs.find(item => item.id === id);
    return { key: `${field}-${id}`, attribute: attr?.name || id, mode: field === "selections" ? "Selected" : "Vary", value: ids.map(value => attr?.values.find(item => item.id === value)?.name || value).join(", ") };
  }));
  return <div className="migration-controls"><h3>Controls to apply</h3>{rows.length ? <table><caption className="sr-only">Resolved selections and variations</caption><thead><tr><th>Attribute</th><th>Mode</th><th>Value</th></tr></thead><tbody>{rows.map(row => <tr key={row.key}><th scope="row">{row.attribute}</th><td>{row.mode}</td><td>{row.value}</td></tr>)}</tbody></table> : <p>No attribute selections.</p>}<p>{draft.mode} · {draft.n} image{draft.n === 1 ? "" : "s"} · {draft.aspect_ratio}{draft.seed === undefined ? "" : ` · Seed ${draft.seed}`}</p>{draft.extra_prompt && <p>Note: {draft.extra_prompt}</p>}{draft.comparison && <section aria-label="Saved comparison anchor"><h3>Comparison anchor</h3><dl><dt>Category</dt><dd>{library.categories.find(category => category.id === draft.comparison?.category_id)?.name || draft.comparison.category_id}</dd><dt>Baseline asset</dt><dd>{draft.comparison.baseline_asset_id}</dd><dt>Contract hash</dt><dd>{draft.comparison.contract_hash}</dd><dt>Locked fields</dt><dd>{draft.comparison.locked_fields.join(", ") || "None"}</dd></dl></section>}</div>;
}

export function MigrationReview({ source, library, onApply, onCancel }: {
  source: MigrationSource | null; library: Library; onApply: (draft: Draft) => void; onCancel: () => void;
}) {
  const [result, setResult] = useState<MigrationResult | null>(null);
  const [resolvedSource, setResolvedSource] = useState<MigrationSource | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const origin = useRef<HTMLElement | null>(null);
  const callbacks = useRef({ onApply, onCancel });
  callbacks.current = { onApply, onCancel };
  useEffect(() => {
    if (!source) { setResult(null); setResolvedSource(null); setError(""); setLoading(false); return; }
    const controller = new AbortController();
    setResult(null); setResolvedSource(null); setError(""); setLoading(true);
    resolveMigration(source, library, controller.signal).then(next => {
      if (controller.signal.aborted) return;
      // Supported v1 records keep the established one-action Apply contract.
      if (next.legacy && !next.unresolved.length) callbacks.current.onApply(next.draft);
      else { setResult(next); setResolvedSource(source); }
    }).catch(failure => {
      if (!controller.signal.aborted) setError(errorMessage(failure));
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [source, library, retry]);
  const currentResult = resolvedSource === source ? result : null;
  return <Dialog.Root open={!!source} onOpenChange={open => { if (!open) onCancel(); }}><Dialog.Portal><Dialog.Overlay className="dialog-overlay migration-overlay" /><Dialog.Content className="dialog-content migration-dialog" onOpenAutoFocus={() => { origin.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; }} onCloseAutoFocus={event => { event.preventDefault(); if (origin.current?.isConnected) origin.current.focus(); }}>
    <Dialog.Title>Review catalog migration</Dialog.Title>
    <Dialog.Description>{source?.name}: review the current catalog controls before changing your composition. The original archive remains intact.</Dialog.Description>
    <Dialog.Close className="icon-button dialog-close" aria-label="Close migration review"><X size={19} /></Dialog.Close>
    <div className="migration-scroll" aria-busy={loading}>
      {loading && <p role="status">Resolving archived controls…</p>}
      {error && <div role="alert"><p>Migration review unavailable: {error}</p><p>Your composition and original record have been kept.</p><button className="secondary" onClick={() => setRetry(value => value + 1)}>Retry migration review</button></div>}
      {currentResult && <>
        {currentResult.legacy && <p className="field-help">Legacy installation: the catalog migration service is unavailable. Known controls use the installed library; unresolved fields stay in the archive.</p>}
        <section aria-label="Catalog migration changes"><h3>Catalog changes</h3><ResolutionList items={currentResult.changes} empty="No catalog changes are needed." /></section>
        <section aria-label="Unresolved preset controls"><h3>Unresolved controls</h3><ResolutionList items={currentResult.unresolved} empty="All archived controls are resolved." />{currentResult.unresolved.length > 0 && <p>Applying known controls omits the unresolved fields from this composition. They remain in the saved archive.</p>}</section>
        <AppliedControls draft={currentResult.draft} library={library} />
      </>}
    </div>
    <div className="dialog-actions"><button className="secondary" onClick={onCancel}>Cancel apply</button><button className="primary" disabled={loading || !currentResult || !!error} onClick={() => { if (currentResult) onApply(currentResult.draft); }}>{currentResult?.unresolved.length ? "Apply known controls" : "Apply resolved controls"}</button></div>
  </Dialog.Content></Dialog.Portal></Dialog.Root>;
}
