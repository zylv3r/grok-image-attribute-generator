import { useEffect, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Bookmark, Check, Trash2, X } from "../icons";
import { api, errorMessage, presetRequest } from "../lib";
import type { Draft, LegacyPresets, Library, Preset, PresetResponse } from "../types";
import { MigrationReview, type MigrationSource } from "./MigrationReview";

export function Presets({ library, draft, change, legacy }: {
  library: Library; draft: Draft; change: (draft: Draft) => void; legacy: LegacyPresets | null;
}) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [importError, setImportError] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [review, setReview] = useState<Preset | null>(null);
  const [migrationSource, setMigrationSource] = useState<MigrationSource | null>(null);
  const requestLock = useRef(false);
  const pending = useRef<ReturnType<typeof presetRequest> | null>(null);
  const [saveFailed, setSaveFailed] = useState(false);

  function acceptList(response: PresetResponse) {
    if (!Array.isArray(response.presets)) throw Error("The server returned an unreadable preset list.");
    setPresets(response.presets);
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setLoadError("");
    async function load() {
      try {
        const response = await api<PresetResponse>("/api/presets", { signal: controller.signal });
        if (controller.signal.aborted) return;
        acceptList(response);
        if (legacy) {
          try {
            const imported = await api<PresetResponse>("/api/presets/import", {
              method: "POST", body: JSON.stringify(legacy), signal: controller.signal,
            });
            if (controller.signal.aborted) return;
            acceptList(imported); setWarnings(imported.warnings || []); setImportError("");
          } catch (error) {
            if (!controller.signal.aborted) setImportError(errorMessage(error));
          }
        }
      } catch (error) {
        if (!controller.signal.aborted) setLoadError(errorMessage(error));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [legacy, revision]);

  async function retryImport() {
    if (!legacy || requestLock.current || loading) return;
    requestLock.current = true; setBusy(true);
    try {
      const response = await api<PresetResponse>("/api/presets/import", { method: "POST", body: JSON.stringify(legacy) });
      acceptList(response); setWarnings(response.warnings || []); setImportError("");
    } catch (error) { setImportError(errorMessage(error)); }
    finally { requestLock.current = false; setBusy(false); }
  }

  async function save() {
    if (requestLock.current || loading || !name.trim()) return;
    requestLock.current = true; setBusy(true); setStatus("Saving…");
    // Capture once. Retry resends the same key AND same payload, even if the editor changes.
    try {
      pending.current ||= presetRequest(name, draft);
      const preset = await api<Preset>("/api/presets", { method: "POST", body: JSON.stringify(pending.current) });
      if (!preset.id || !preset.draft) throw Error("The server did not confirm a saved preset.");
      setPresets(previous => [...previous.filter(p => p.id !== preset.id), preset]);
      pending.current = null; setSaveFailed(false); setName("");
      setStatus("Preset saved on this studio.");
    } catch (error) {
      setSaveFailed(true); setStatus(`Save failed: ${errorMessage(error)} Retry keeps the captured name and controls.`);
    } finally { requestLock.current = false; setBusy(false); }
  }

  async function remove(preset: Preset) {
    if (requestLock.current || loading) return;
    requestLock.current = true; setBusy(true);
    try {
      acceptList(await api<PresetResponse>(`/api/presets/${encodeURIComponent(preset.id)}`, { method: "DELETE", body: "{}" }));
      setStatus("Preset deleted from this studio.");
      if (review?.id === preset.id) { setReview(null); setMigrationSource(null); }
    } catch (error) { setStatus(`Delete failed: ${errorMessage(error)} Retry with Delete.`); }
    finally { requestLock.current = false; setBusy(false); }
  }

  function apply(preset: Preset) {
    setReview(preset);
    setMigrationSource({ name: preset.name, draft: preset.draft, schemaVersion: preset.schema_version });
  }

  return <><Dialog.Root open={open} onOpenChange={next => { setOpen(next); if (!next) { setReview(null); setMigrationSource(null); } }}>
    <Dialog.Trigger asChild><button className="secondary"><Bookmark size={15} />Presets</button></Dialog.Trigger>
    <Dialog.Portal>
      <Dialog.Overlay className="dialog-overlay" />
      <Dialog.Content className="dialog-content preset-dialog">
        <Dialog.Title>Saved on this studio</Dialog.Title>
        <Dialog.Description>Keep selections, allowed variations, and generation settings across browsers and devices.</Dialog.Description>
        <Dialog.Close className="icon-button dialog-close" aria-label="Close presets"><X size={19} /></Dialog.Close>
        <form className="save-preset" onSubmit={event => { event.preventDefault(); void save(); }}>
          <label htmlFor="preset-name" className="field-label">Name this direction</label>
          <div>
            <input id="preset-name" value={name} maxLength={80} disabled={busy} onChange={event => {
              setName(event.target.value); pending.current = null; setSaveFailed(false); setStatus("");
            }} placeholder="e.g. Quiet afternoon" />
            <button className="primary" disabled={busy || loading || !name.trim()} type="submit">{saveFailed ? "Retry save" : "Save preset"}</button>
          </div>
        </form>
        <p role="status" className="muted">{loading ? "Loading presets…" : status || (loadError ? `Presets unavailable: ${loadError}` : "")}</p>
        {loadError && <button className="secondary" disabled={loading || busy} onClick={() => setRevision(v => v + 1)}>Retry loading presets</button>}
        {(importError || warnings.length > 0) && <div>
          <p>Import needs attention. The original browser copy is retained.</p>
          {importError && <p>{importError}</p>}
          {warnings.map((warning, index) => <p key={index}>{warning}</p>)}
          {importError && <button className="secondary" disabled={busy || loading} onClick={() => void retryImport()}>Retry import</button>}
        </div>}
        <div className="preset-list" aria-busy={loading || busy}>
          {presets.map(preset => <div key={preset.id}>
            <div><strong>{preset.name}</strong></div>
            <button className="secondary" disabled={busy || loading} aria-label={`Apply ${preset.name}`} onClick={() => apply(preset)}>Apply<Check size={14} /></button>
            <button className="icon-button" disabled={busy || loading} aria-label={`Delete ${preset.name}`} onClick={() => void remove(preset)}><Trash2 size={15} /></button>
          </div>)}
          {!loading && !loadError && !presets.length && <p className="muted">No presets yet. Save your current composition above.</p>}
        </div>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root><MigrationReview source={migrationSource} library={library} onCancel={() => { setReview(null); setMigrationSource(null); }} onApply={resolved => { change(resolved); setReview(null); setMigrationSource(null); setOpen(false); }} /></>;
}
