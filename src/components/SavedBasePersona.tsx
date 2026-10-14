import { useEffect, useState } from "react";
import "./saved-base.css";
type SavedBase = { available: boolean; id?: string; revision?: number; title?: string; overview_url?: string; pdf_url?: string; canonical_face_url?: string; canonical_body_url?: string; future_image_model?: string; keywords?: string[]; caveats?: string[] };
export function SavedBasePersona() {
  const [base, setBase] = useState<SavedBase>();
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/base-persona", { signal: controller.signal, cache: "no-store" })
      .then(async response => { if (!response.ok) return { available: false }; return response.json() as Promise<SavedBase>; })
      .then(setBase).catch(e => { if (e.name !== "AbortError") setError("Saved reference is temporarily unavailable."); });
    return () => controller.abort();
  }, []);
  return <section className="saved-base" aria-label="Saved persona reference">
    <div className="saved-base-copy"><span className="eyebrow">CANONICAL REFERENCE</span>
      <h2>{base?.available ? `Persona B · reference v${base.revision}` : "Imagine 2.0 image policy"}</h2>
      <p>Future app generation and reference edits use <strong>grok-imagine-image-2.0</strong>; no legacy-model fallback.</p>
      {base?.available && <><p>{base.keywords?.join(" · ")}</p><p>Selected reference set for iteration. Existing source models and known limitations are preserved; selection does not approve group masks or publication.</p>
        <div className="saved-base-links"><a href={base.pdf_url} target="_blank" rel="noopener noreferrer">Reference sheet PDF</a><a href={base.canonical_face_url} target="_blank" rel="noopener noreferrer">Face original</a><a href={base.canonical_body_url} target="_blank" rel="noopener noreferrer">Body original</a></div>
        <details><summary>Known limitations and approval boundary</summary><ul>{base.caveats?.map(c => <li key={c}>{c}</li>)}</ul></details></>}
      <p className="saved-base-mode">Saved reference metadata is not automatically an image input. Ordinary Studio generation is text-to-image; reference edits must explicitly supply the original and pass the applicable review gates.</p>
      {error && <p role="status">{error}</p>}
    </div>
    {base?.available && base.overview_url && <a className="saved-base-preview" href={base.overview_url} target="_blank" rel="noopener noreferrer" aria-label="Open Persona B master reference sheet"><img src={base.overview_url} alt="Persona B selected iterative reference sheet, with provisional views and known caveats" /></a>}
  </section>;
}
