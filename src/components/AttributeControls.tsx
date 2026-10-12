import { useState } from "react";
import type { CSSProperties } from "react";
import type { Attribute, Draft, Value } from "../types";
import { setAttribute } from "../lib";
import "./attribute-controls.css";

type ControlProps = { attr: Attribute; draft: Draft; target: "selections" | "whitelist"; ids: string[]; change: (draft: Draft) => void };

function declaredDefaultName(attr: Attribute): string | undefined {
  const defaults = typeof attr.default === "string" ? [attr.default] : attr.default;
  if (!Array.isArray(defaults) || !defaults.length) return;
  return defaults.map(id => attr.values.find(value => value.id === id)?.name || id).join(", ");
}

function ageNumber(id: string | undefined) {
  const match = /^age_(\d+)$/.exec(id || "");
  return match ? Number(match[1]) : undefined;
}

export function RangeControl({ attr, draft, target, ids, change }: ControlProps) {
  const range = attr.range!;
  const defaultName = declaredDefaultName(attr);
  const selected = ageNumber(ids[0]);
  const [numberDraft, setNumberDraft] = useState({ selected, text: selected === undefined ? "" : String(selected) });
  const [notice, setNotice] = useState("");
  if (numberDraft.selected !== selected) {
    setNumberDraft({ selected, text: selected === undefined ? "" : String(selected) });
    setNotice("");
  }
  const numberText = numberDraft.text;
  const defaultAge = ageNumber(typeof attr.default === "string" ? attr.default : attr.default?.[0]);
  const dialAge = selected ?? (defaultAge !== undefined && attr.values.some(v => v.id === `age_${defaultAge}`) ? defaultAge : range.min);
  const allowedAges = ids.map(ageNumber).filter((n): n is number => n !== undefined);
  const [minimum, setMinimum] = useState(String(allowedAges.length ? Math.min(...allowedAges) : range.min));
  const [maximum, setMaximum] = useState(String(allowedAges.length ? Math.max(...allowedAges) : range.max));
  function validAge(raw: string) {
    const number = Number(raw);
    return !!raw && Number.isInteger(number) && number >= range.min && number <= range.max && (number - range.min) % range.step === 0 && attr.values.some(v => v.id === `age_${number}`);
  }
  function choose(raw: string, reportInvalid = true) {
    if (raw && !validAge(raw)) { if (reportInvalid) setNotice(`Choose a whole age from ${range.min} to ${range.max}.`); return; }
    setNotice("");
    // Bind local text to its committed value so parent updates retain the typing draft.
    setNumberDraft({ selected: raw ? Number(raw) : undefined, text: raw });
    change(setAttribute(draft, attr, target, raw ? [`age_${Number(raw)}`] : []));
  }
  function useRange() {
    const min = Number(minimum), max = Number(maximum);
    if (!minimum || !maximum || !Number.isInteger(min) || !Number.isInteger(max) || min < range.min || max > range.max || min > max) {
      setNotice(`Enter an ordered range from ${range.min} to ${range.max}.`);
      return;
    }
    const values = attr.values.filter(value => { const age = ageNumber(value.id); return age !== undefined && age >= min && age <= max; }).map(value => value.id);
    change(setAttribute(draft, attr, "whitelist", values));
    setNotice(`${values.length} canonical ages allowed, ${min}–${max}.`);
  }
  return <div className="numeric-attribute">
    <p className="attribute-description">Adult age {range.min}–{range.max}. Generation control only; comparison baselines remain adult women. No age photographs.</p>
    {!ids.length && defaultName && <p>Unset omits this control; generation uses the catalog default: {defaultName}.</p>}
    {target === "selections" ? <>
      <label htmlFor={`dial-${attr.id}`}>{attr.name} dial <output>{selected === undefined ? "Unset" : `${selected} years`}</output></label>
      <input id={`dial-${attr.id}`} type="range" aria-label={`${attr.name} dial`} min={range.min} max={range.max} step={range.step} value={dialAge} aria-valuetext={selected === undefined ? `Unset; catalog default ${dialAge} years. Move the slider to choose an adult age` : `${selected} years`} onChange={event => choose(event.target.value)} onPointerUp={event => choose(event.currentTarget.value)} onKeyDown={event => { if (event.key === "Home" || event.key === "End") { event.preventDefault(); choose(String(event.key === "Home" ? range.min : range.max)); } }} />
      <label htmlFor={`numeric-${attr.id}`}>{attr.name} in years</label>
      <input id={`numeric-${attr.id}`} aria-describedby={`numeric-status-${attr.id}`} aria-invalid={!!notice && !!numberText && !validAge(numberText)} type="number" min={range.min} max={range.max} step={range.step} value={numberText} onFocus={() => setNotice("")} onChange={event => { setNumberDraft({ selected, text: event.target.value }); setNotice(""); choose(event.target.value, false); }} onBlur={() => { if (numberText && !validAge(numberText)) { choose(numberText); setNumberDraft({ selected, text: selected === undefined ? "" : String(selected) }); } }} />
    </> : <>
      <div className="age-range-inputs">
        <label htmlFor={`minimum-${attr.id}`}>Minimum allowed {attr.name}<input id={`minimum-${attr.id}`} type="number" min={range.min} max={range.max} step={range.step} value={minimum} onChange={event => setMinimum(event.target.value)} /></label>
        <label htmlFor={`maximum-${attr.id}`}>Maximum allowed {attr.name}<input id={`maximum-${attr.id}`} type="number" min={range.min} max={range.max} step={range.step} value={maximum} onChange={event => setMaximum(event.target.value)} /></label>
        <button type="button" className="secondary" onClick={useRange}>Use age range</button>
      </div>
      <p>{ids.length ? `Allowed ages: ${allowedAges.join(", ")}` : "No allowed ages. Choose a range or use All."}</p>
    </>}
    <button type="button" className="secondary" aria-label={`Unset ${attr.name}`} onClick={() => { setNumberDraft({ selected: undefined, text: "" }); setNotice(""); change(setAttribute(draft, attr, target, [])); }}>None / unset</button>
    <p id={`numeric-status-${attr.id}`} role="status">{notice}</p>
  </div>;
}

export function SelectControl({ attr, draft, target, ids, change }: ControlProps) {
  const multiple = target === "whitelist" || attr.type === "multi";
  const defaultName = declaredDefaultName(attr);
  return <div className="select-attribute">
    <label htmlFor={`select-${attr.id}`}>{attr.name} {multiple ? "allowed values" : "value"}</label>
    <select id={`select-${attr.id}`} multiple={multiple} value={multiple ? ids : ids[0] || ""} size={multiple ? Math.min(6, attr.values.length + 1) : undefined} onChange={event => change(setAttribute(draft, attr, target, multiple ? Array.from(event.target.selectedOptions).map(option => option.value).filter(Boolean) : event.target.value ? [event.target.value] : []))}>
      {!multiple && <option value="">None / unset</option>}
      {attr.values.map(value => <option key={value.id} value={value.id}>{value.name}</option>)}
    </select>
    {!ids.length && defaultName && <p>Unset omits this control; generation uses the catalog default: {defaultName}.</p>}
    {multiple && <p>Use Control or Command to select several values; Shift selects a range.</p>}
    {attr.id === "gender" && <p className="attribute-description">Presentation can vary in actual generation. Every comparison sample uses an adult woman baseline. This control has no photo preview.</p>}
    {ids.map(id => { const value = attr.values.find(v => v.id === id); return value ? <p key={id}>{value.description || value.steers}</p> : null; })}
    <button type="button" className="secondary" aria-label={`Unset ${attr.name}`} onClick={() => change(setAttribute(draft, attr, target, []))}>None / unset</button>
  </div>;
}

export function swatchRGB(value: Value): string | undefined {
  const previewParams = value.preview_params && typeof value.preview_params === "object" && !Array.isArray(value.preview_params) ? value.preview_params as Record<string, unknown> : undefined;
  const colour = value.colour || previewParams?.colour;
  const nestedColour = colour && typeof colour === "object" && !Array.isArray(colour) ? (colour as Record<string, unknown>).hex : colour;
  const raw = value.rgb || value.color || value.hex || nestedColour;
  if (Array.isArray(raw) && raw.length === 3 && raw.every(channel => Number.isInteger(channel) && channel >= 0 && channel <= 255)) return raw.join(", ");
  if (typeof raw === "string") {
    const hex = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(raw);
    if (hex) return hex.slice(1).map(channel => parseInt(channel, 16)).join(", ");
    const triple = /^(?:rgb\()?\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)?$/.exec(raw);
    if (triple && triple.slice(1).every(channel => Number(channel) <= 255)) return triple.slice(1).map(Number).join(", ");
  }
  return undefined;
}

export function FabricSwatch({ value }: { value: Value }) {
  const rgb = swatchRGB(value);
  const candidate = value.thumbnail_url || value.thumbnail;
  const [failed, setFailed] = useState<string>();
  const controlled = candidate && /^\/api\/comparisons\/assets\/[a-f0-9]{32}\.png$/.test(candidate) && failed !== candidate && value.thumbnail_status !== "pending" && value.thumbnail_status !== "failed";
  return <span className="swatch-preview">{controlled ? <img className="fabric-swatch" src={candidate} alt={`${value.name}: controlled fabric patch`} onError={() => setFailed(candidate)} /> : <span className="fabric-swatch" aria-hidden="true" style={{ backgroundColor: rgb ? `rgb(${rgb})` : "#c3bdb3" } as CSSProperties} />}<span className="swatch-rgb">{rgb ? `RGB ${rgb}` : "RGB not supplied"}</span><span className="swatch-rgb">{controlled ? "Controlled PNG patch" : "Simulated texture patch"}</span></span>;
}

export function FashionAvatar({ attr, value }: { attr: Attribute; value: Value }) {
  const words = `${value.id} ${value.name}`.toLowerCase();
  const amount = /broad|wide|full|large|high|strong/.test(words) ? 1 : /narrow|slim|small|low|slender/.test(words) ? -1 : 0;
  const shoulder = /shoulder|frame/.test(attr.id) ? amount * 4 : 0;
  const hip = /hip|fullness|body_build|figure/.test(attr.id) ? amount * 4 : 0;
  const waist = /waist/.test(attr.id) ? amount * 3 : 0;
  const bust = /bust/.test(attr.id) ? amount * 3 : 0;
  const calf = /calf/.test(attr.id) ? amount * 2 : 0;
  const legRatio = /leg.*torso|torso.*leg|leg.*balance/.test(attr.id) ? amount * 5 : 0;
  const thigh = /thigh/.test(attr.id) ? amount * 3 : 0;
  const height = /stature/.test(attr.id) ? amount * 4 : 0;
  return <svg className="fashion-avatar" viewBox="0 0 90 130" aria-hidden="true" focusable="false">
    <circle cx="45" cy="16" r="9" fill="#baa18e" />
    <path d={`M${29 - shoulder} 33 Q45 28 ${61 + shoulder} 33 L${67 + shoulder} 71 L${61 + shoulder} 74 L${56 + shoulder} 46 Q${58 + bust} 51 ${54 + waist} ${64 - legRatio} L${58 + hip} ${84 - legRatio} L${57 + thigh} 100 L${55 + calf} ${118 + height} L47 ${118 + height} L45 ${86 - legRatio} L43 ${118 + height} L${35 - calf} ${118 + height} L${33 - thigh} 100 L${32 - hip} ${84 - legRatio} L${36 - waist} ${64 - legRatio} Q${32 - bust} 51 ${34 - shoulder} 46 L${29 - shoulder} 74 L${23 - shoulder} 71Z`} fill="#5e7075" stroke="#344649" strokeWidth="1.5" />
    <path d={`M${36 - waist} ${64 - legRatio}H${54 + waist} M45 ${86 - legRatio}V113`} fill="none" stroke="#b4c0c2" />
  </svg>;
}

export function recipeSelections(value: Value): Record<string, string[]> | undefined {
  const recipe: unknown = value.recipe;
  if (!recipe || typeof recipe !== "object" || Array.isArray(recipe)) return;
  const nested = (recipe as Record<string, unknown>).selections;
  const candidate = nested && typeof nested === "object" && !Array.isArray(nested) ? nested : recipe;
  const entries = Object.entries(candidate);
  if (!entries.length || !entries.every(([, ids]) => Array.isArray(ids) && ids.every(id => typeof id === "string"))) return;
  return Object.fromEntries(entries) as Record<string, string[]>;
}

export function RecipeDisclosure({ value }: { value: Value }) {
  if (!value.recipe) return null;
  const components = recipeSelections(value);
  const allowed = typeof value.recipe === "object" ? value.recipe.allowed_component_changes : undefined;
  return <span className="recipe-disclosure"><strong>Explicit recipe</strong>{typeof value.recipe === "string" ? <span>{value.recipe}</span> : components ? Object.entries(components).map(([id, values]) => <span key={id}>{id}: {values.join(", ")}</span>) : <span>Recipe metadata unavailable; component application is disabled.</span>}{Array.isArray(allowed) && <span>Allowed component changes: {allowed.join(", ")}</span>}<span>Review component overrides before applying. Historical recipe migration requires review.</span></span>;
}

export function sourceLabel(attr: Attribute) {
  if (attr.preview_scope === "control_only" || attr.control === "range" || attr.id === "gender") return "Control only · no photograph";
  const declaredSource = attr.thumbnail_source || attr.sample_source || attr.preview_status || attr.preview_source;
  if (attr.control === "swatch") return declaredSource === "approved_comparison" ? "Published controlled fabric swatches" : "Simulated texture / RGB swatches";
  if (declaredSource === "approved_comparison") return "Published controlled comparisons";
  if (declaredSource === "legacy_independent_photo" || declaredSource === "legacy_independent" || attr.preview_method === "legacy_independent_photo") return "Legacy exploratory photographs";
  if (attr.preview_method === "reference_edit") return "Reference edit · operator approval required";
  return attr.control || attr.preview_method ? "Draft controls · comparison review required" : undefined;
}
