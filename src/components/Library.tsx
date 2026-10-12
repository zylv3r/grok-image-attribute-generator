import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as Checkbox from "@radix-ui/react-checkbox";
import { Check, ChevronDown, LockKeyhole, Shuffle } from "../icons";
import { Attribute, Category, Draft, Library } from "../types";
import { bulkVary, matchingValues, previewLabel, setAttribute } from "../lib";
import { Thumb } from "./UI";
import { FabricSwatch, FashionAvatar, RangeControl, RecipeDisclosure, SelectControl, recipeSelections, sourceLabel } from "./AttributeControls";
const pageSize = 12;
const photoThumbnail = /^\/generated\/[a-f0-9]{32}-thumb\.jpg$/;
const photoOriginal = /^\/generated\/[a-f0-9]{32}\.jpg$/;
const contactSheet = /^\/preview-atlases\/[a-zA-Z0-9_-]+\.jpg(?:\?v=\d+)?$/;
const comparisonAsset = /^\/api\/comparisons\/assets\/[a-f0-9]{32}\.png$/;
function AttributeEditor({ attr, draft, change, query, open, setOpen, photographic, bodyGuide = false, catalogAttributes }: {
  attr: Attribute; draft: Draft; change: (d: Draft) => void; query: string;
  open: boolean; setOpen: (open: boolean) => void;
  photographic: boolean; bodyGuide?: boolean; catalogAttributes: Attribute[];
}) {
  const [limit, setLimit] = useState(pageSize);
  const [lastQuery, setLastQuery] = useState(query);
  const [notice, setNotice] = useState("");
  const [recipeValue, setRecipeValue] = useState<Attribute["values"][number] | null>(null);
  const recipeReturnFocus = useRef<HTMLElement | null>(null);
  function openRecipe(value: Attribute["values"][number]) {
    recipeReturnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setRecipeValue(value);
  }
  if (lastQuery !== query) {
    setLastQuery(query);
    setLimit(pageSize);
  }
  const target = draft.selections[attr.id] ? "selections" : draft.whitelist[attr.id] ? "whitelist" : draft.attributeModes?.[attr.id] || "selections";
  const ids = draft[target][attr.id] || [];
  const isCheck = target === "whitelist" || attr.type === "multi";
  const rangeControl = attr.control === "range" && !!attr.range;
  const selectControl = attr.control === "select";
  const swatchControl = attr.control === "swatch";
  const bodyControl = bodyGuide || attr.comparison_group === "body" || attr.preview_method === "fashion_avatar";
  const specialControl = rangeControl || selectControl;
  const source = sourceLabel(attr);
  const hasRecipe = attr.values.some(value => !!value.recipe);
  const matches = matchingValues(attr, query);
  const values = attr.values.filter((v) => matches.includes(v) || ids.includes(v.id));
  const shown = values.filter((v, index) => index < limit || ids.includes(v.id));
  const remaining = values.length - shown.length;
  const descriptionId = `attribute-description-${attr.id}`;
  const behaviorId = `attribute-behavior-${attr.id}`;
  const unsetId = `attribute-unset-${attr.id}`;
  function select(id: string) {
    const recipe = attr.values.find(value => value.id === id && value.recipe);
    if (recipe && target === "selections") { openRecipe(recipe); return; }
    change(setAttribute(draft, attr, target, id === "__none" ? [] : [id]));
  }
  const recipeComponents = recipeValue ? recipeSelections(recipeValue) : undefined;
  const recipeValid = !!recipeComponents && Object.entries(recipeComponents).every(([id, values]) => {
    const component = catalogAttributes.find(attribute => attribute.id === id);
    return !!component && id !== attr.id && values.length > 0 && (component.type === "multi" || values.length === 1) && values.every(value => component.values.some(candidate => candidate.id === value));
  });
  function applyRecipe() {
    if (!recipeValue || !recipeComponents || !recipeValid) return;
    let next = setAttribute(draft, attr, "selections", [recipeValue.id]);
    for (const [id, values] of Object.entries(recipeComponents)) next = setAttribute(next, catalogAttributes.find(attribute => attribute.id === id)!, "selections", values);
    change(next);
    setNotice(`Applied ${recipeValue.name} and ${Object.keys(recipeComponents).length} declared component locks. Other controls retained.`);
    setRecipeValue(null);
  }
  function move(next: "selections" | "whitelist") {
    const removed = next === "selections" && attr.type !== "multi" ? Math.max(0, ids.length - 1) : 0;
    setNotice(removed ? `Switched to Lock. Kept ${attr.values.find((v) => v.id === ids[0])?.name}; removed ${removed} allowed ${removed === 1 ? "value" : "values"}.` : `Switched to ${next === "whitelist" ? "Vary" : "Lock"}. ${ids.length ? "Choices retained." : "No values selected."}`);
    change(setAttribute(draft, attr, next, ids));
  }
  function navigate(event: KeyboardEvent<HTMLDivElement>) {
    if (!['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp', 'Home', 'End'].includes(event.key) || event.altKey || event.ctrlKey || event.metaKey) return;
    const controls = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="radio"]'));
    const index = controls.indexOf(event.target as HTMLButtonElement);
    if (index < 0) return;
    event.preventDefault();
    // Commit focus and selection in the same keydown; keyup timing cannot change selection.
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? controls.length - 1 : (index + (event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1 : -1) + controls.length) % controls.length;
    controls[next].focus();
    select(controls[next].dataset.value!);
  }
  const contents = shown.map((v) => {
    const valueDescription = `value-description-${attr.id}-${v.id}`;
    const controlOnly = attr.preview_method === "control_only" || attr.control === "range" || attr.id === "gender";
    const candidate = v.thumbnail_url || v.thumbnail;
    const status = v.thumbnail_status || v.status;
    const bodyControlled = bodyControl && comparisonAsset.test(candidate || "") && status !== "pending" && status !== "failed";
    const isPhoto = bodyControlled || (!controlOnly && !bodyControl && !swatchControl && (photographic || v.thumbnail_mode === "photographic" || v.thumbnail_kind === "photographic"));
    const url = controlOnly ? undefined : isPhoto ? (status !== "pending" && status !== "failed" && (photoThumbnail.test(candidate || "") || comparisonAsset.test(candidate || "")) ? candidate : undefined) : candidate;
    const exampleUrl = url && (photoOriginal.test(v.example_url || "") || comparisonAsset.test(v.example_url || "")) ? v.example_url : undefined;
    const swatchColor = typeof v.color === "string" ? v.color : v.hex || (Array.isArray(v.color) ? `rgb(${v.color.join(",")})` : undefined);
    const exampleDescription = `value-example-${attr.id}-${v.id}`;
    const inner = <>
      {swatchControl ? <FabricSwatch value={v} /> : bodyControl ? bodyControlled ? <Thumb url={url} name={v.name} photographic alt={`${previewLabel({...attr,...v})}: ${v.name}`} /> : <FashionAvatar attr={attr} value={v} /> : !controlOnly && <Thumb url={url} name={v.name} photographic={isPhoto} alt={isPhoto && url ? `${previewLabel({...attr,...v})}: ${v.name}` : ""} />}
      <span className="value-copy"><strong>{v.name}</strong>{isPhoto && <span id={exampleDescription} className="example-label">{url ? previewLabel({...attr,...v}) : "Comparison pending"}</span>}<span id={valueDescription}>{v.description || v.steers}</span>{bodyControl && !bodyControlled && <span className="example-label">Clothed schematic · illustrative</span>}<RecipeDisclosure value={v} /></span>
      <span className={`value-indicator ${isCheck ? "square" : ""}`} aria-hidden="true">{ids.includes(v.id) && <Check size={12} />}</span>
    </>;
    const describedBy = `${valueDescription} ${behaviorId}${isPhoto ? ` ${exampleDescription}` : ""}`;
    const control = isCheck ? <Checkbox.Root key={v.id} className="value-card" aria-label={v.name} aria-describedby={describedBy} checked={ids.includes(v.id)} onCheckedChange={(checked) => change(setAttribute(draft, attr, target, checked === true ? [...ids, v.id] : ids.filter((id) => id !== v.id)))}>{inner}</Checkbox.Root>
      : <button key={v.id} type="button" role="radio" className="value-card" data-value={v.id} data-state={ids.includes(v.id) ? "checked" : "unchecked"} aria-label={v.name} aria-describedby={describedBy} aria-checked={ids.includes(v.id)} tabIndex={ids[0] === v.id ? 0 : -1} onClick={() => select(v.id)}>{inner}</button>;
    const recipeAction = v.recipe && <button type="button" className="secondary" onClick={() => openRecipe(v)}>Apply {v.name} recipe components</button>;
    if (recipeAction) return <div key={v.id} className="recipe-value">{control}{recipeAction}</div>;
    return isPhoto ? <div key={v.id} className="photographic-value">{control}{exampleUrl && <a className="example-link" href={exampleUrl} target="_blank" rel="noopener noreferrer" aria-label={`Open original generated example: ${v.name}`}>Open original</a>}</div> : control;
  });
  const attrCandidate = attr.thumbnail_url || attr.thumbnail;
  const attrStatus = attr.thumbnail_status || attr.status;
  const noImages = attr.preview_method === "control_only" || attr.control === "range" || attr.id === "gender" || attr.control === "swatch";
  const attrUrl = noImages ? undefined : photographic ? (attrStatus !== "pending" && attrStatus !== "failed" && (contactSheet.test(attrCandidate || "") || comparisonAsset.test(attrCandidate || "")) ? attrCandidate : undefined) : attrCandidate;
  const headingHasThumb = !specialControl && !swatchControl && !bodyControl;
  const summary = ids.length ? `${target === "whitelist" ? "Vary" : "Locked"}: ${attr.values.filter((v) => ids.includes(v.id)).map((v) => v.name).join(", ")}` : `${target === "whitelist" ? "Vary" : "Lock"} · None / unset`;
  return <section className="attribute" aria-label={attr.name} id={`attribute-${attr.id}`} onClick={() => { if (!open) setOpen(true); }}>
    <h3><button type="button" className="attribute-heading attribute-toggle" aria-label={`Edit ${attr.name}`} aria-describedby={`attribute-summary-${attr.id}`} aria-expanded={open} aria-controls={`attribute-values-${attr.id}`} onClick={(event) => { event.stopPropagation(); setOpen(!open); }}>
      {!noImages && headingHasThumb && <Thumb url={attrUrl} name={attr.name} className="attribute-thumb" photographic={photographic} pendingLabel="Contact sheet pending" alt={photographic && attrUrl ? `${attr.name}: representative examples` : ""} />}
      <span className="attribute-title"><strong>{attr.name}</strong>{source && <span className="attribute-source">{source}</span>}{photographic && !noImages && <span className="representative-label">{attrUrl ? previewLabel(attr) : "Comparison pending"}</span>}<span className="attribute-summary" id={`attribute-summary-${attr.id}`}>{summary}</span></span>
      <span className="type-label">{attr.values.length} values · {attr.type === "multi" ? "Multiple" : attr.type === "boolean" ? "Explicit choice" : "Choose one"}</span>
      <ChevronDown size={16} className={open ? "expanded-chevron" : ""} aria-hidden="true" />
    </button></h3>
    <div id={`attribute-values-${attr.id}`} hidden={!open}>
      {open && <>
        <p id={descriptionId} className="attribute-description">{attr.description || (attr.type === "multi" ? "Combine any number of values." : attr.type === "boolean" ? "Choose an explicit value, or leave unset. Unset does not mean off." : "Choose one value, or leave unset.")}</p>
        {source && <div className="attribute-schema"><span>{source}</span>{attr.comparison_group && <span>Review group: {attr.comparison_group}</span>}{attr.preview_method && <span>Method: {attr.preview_method}</span>}{attr.preview_scope && <span>Scope: {attr.preview_scope}</span>}</div>}
        {hasRecipe && <p className="recipe-warning">These choices are explicit recipes of component controls. Review their declared changes and any migration warnings; a recipe is not an independently locked physical attribute.</p>}
        <div className="attribute-tools">
          <div className="segmented small" role="group" aria-label={`${attr.name} behavior`}>
            <button aria-pressed={target === "selections"} onClick={() => move("selections")}><LockKeyhole size={12} />Lock</button>
            <button aria-pressed={target === "whitelist"} onClick={() => move("whitelist")}><Shuffle size={12} />Vary</button>
          </div>
          <p id={behaviorId}>{target === "whitelist" ? `Only checked values are allowed. ${ids.length === 1 ? "One allowed value is deliberate: it stays the same in each plan. Add more to vary this attribute." : "Pick two or more for different plans."}` : "Selected values stay fixed in every image."}</p>
        </div>
        {target === "whitelist" && <div className="attribute-tools" role="group" aria-label={`${attr.name} whole attribute variations`}>
          <button type="button" className="secondary" onClick={() => change(bulkVary(draft, attr, "all"))}>All {attr.values.length} values</button>
          <button type="button" className="secondary" onClick={() => change(bulkVary(draft, attr, "none"))}>None</button>
          <button type="button" className="secondary" onClick={() => change(bulkVary(draft, attr, "inverse"))}>Inverse across {attr.values.length}</button>
          <p>{ids.length} allowed · {specialControl ? attr.values.length : shown.length} shown; actions affect all {attr.values.length}</p>
        </div>}
        {notice && <p className="attribute-notice" role="status">{notice}</p>}
        {rangeControl ? <RangeControl attr={attr} draft={draft} target={target} ids={ids} change={change} /> : selectControl ? <SelectControl attr={attr} draft={draft} target={target} ids={ids} change={change} /> : <div className="value-grid" role={isCheck ? "group" : "radiogroup"} aria-label={`${attr.name} ${target === "whitelist" ? "allowed variations" : "values"}`} aria-describedby={`${descriptionId} ${behaviorId}`} onKeyDown={isCheck ? undefined : navigate}>
          {contents}
          {isCheck ? <button className={`none-card ${!ids.length ? "active" : ""}`} aria-label={`Unset ${attr.name}`} aria-pressed={!ids.length} aria-describedby={unsetId} onClick={() => { change(setAttribute(draft, attr, target, [])); setNotice("Choices cleared. This attribute adds no instruction; unset does not mean off."); }}>None / unset<span id={unsetId}>No instruction for this attribute</span></button>
            : <button type="button" role="radio" className="none-card" data-value="__none" data-state={!ids.length ? "checked" : "unchecked"} aria-label={`Unset ${attr.name}`} aria-checked={!ids.length} aria-describedby={unsetId} tabIndex={!ids.length ? 0 : -1} onClick={() => select("__none")}>None / unset<span id={unsetId}>No instruction; unset does not mean off</span></button>}
        </div>}
        {remaining > 0 && !(attr.control === "range" || attr.control === "select") && <button className="secondary show-more" onClick={() => setLimit((n) => n + pageSize)}>Show more {attr.name} values ({remaining} remaining)</button>}
        {!specialControl && values.length > pageSize && !(attr.control === "range" || attr.control === "select") && <p className="attribute-description">Showing {shown.length} of {values.length} values{query ? " matching your search or selected" : ""}. Search the library to find any value directly.</p>}
      </>}
    </div>
    <Dialog.Root open={!!recipeValue} onOpenChange={next => { if (!next) setRecipeValue(null); }}>
      <Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="dialog-content recipe-dialog" onCloseAutoFocus={event => { event.preventDefault(); recipeReturnFocus.current?.focus(); }}>
        <Dialog.Title>Apply {recipeValue?.name} recipe</Dialog.Title>
        <Dialog.Description>This explicitly locks the recipe and its declared component controls. Review existing selections that will be replaced before applying.</Dialog.Description>
        {recipeComponents && <ul>{Object.entries(recipeComponents).map(([id, values]) => {
          const component = catalogAttributes.find(attribute => attribute.id === id);
          const previous = draft.selections[id] || draft.whitelist[id] || [];
          return <li key={id}><strong>{component?.name || id}</strong>: {values.map(value => component?.values.find(candidate => candidate.id === value)?.name || value).join(", ")}{previous.length > 0 && <span> · Replaces {draft.whitelist[id] ? "Vary" : "Lock"}: {previous.map(value => component?.values.find(candidate => candidate.id === value)?.name || value).join(", ")}</span>}</li>;
        })}</ul>}
        {!recipeValid && <p role="alert">The declared recipe references unavailable or invalid component controls. It cannot be applied.</p>}
        <div className="dialog-actions"><Dialog.Close asChild><button type="button" className="secondary">Cancel</button></Dialog.Close><button type="button" className="primary" disabled={!recipeValid} onClick={applyRecipe}>Apply recipe and component locks</button></div>
      </Dialog.Content></Dialog.Portal>
    </Dialog.Root>
  </section>;
}
export function LibraryPanel({ category, draft, change, query, photographic = false, library }: { category: Category; library?: Library; draft: Draft; change: (d: Draft) => void; query: string; photographic?: boolean }) {
  const normalized = query.trim().toLowerCase();
  const source = category.catalog_source || category.schema_source || category.source_path || category.source;
  const isV2 = category.attributes.some(attr => !!attr.control || !!attr.comparison_group);
  const [opened, setOpened] = useState<Record<string, boolean>>({});
  const [previousQuery, setPreviousQuery] = useState(normalized);
  if (previousQuery !== normalized) {
    setPreviousQuery(normalized);
    setOpened({});
  }
  const attrs = category.attributes.filter((a) => matchingValues(a, normalized).length > 0 || draft.selections[a.id]?.length || draft.whitelist[a.id]?.length);
  function isOpen(attr: Attribute) {
    return opened[attr.id] ?? (!!normalized || category.attributes.indexOf(attr) < 2 || !!draft.selections[attr.id]?.length || !!draft.whitelist[attr.id]?.length);
  }
  function jump(id: string) {
    if (!id) return;
    setOpened((prev) => ({ ...prev, [id]: true }));
    requestAnimationFrame(() => { const heading = document.querySelector<HTMLButtonElement>(`#attribute-${CSS.escape(id)} .attribute-toggle`); heading?.scrollIntoView({ block: "start", behavior: "auto" }); heading?.focus({ preventScroll: true }); });
  }
  return <>
    <div className="section-heading"><div><span className="eyebrow">THE ATTRIBUTE LIBRARY</span><h2>{category.name}</h2></div><span className="guide-label">{isV2 ? "Draft catalog · category review gates publication" : photographic ? "Generated photographic examples" : "Illustrative guides · not generated results"}</span></div>
    {typeof source === "string" && <p className="attribute-description">Category schema source: {source}</p>}
    {isV2 && <p className="attribute-description">Legacy exploratory samples were independently generated. Each attribute declares its control method; controlled samples require reviewed publication for this category.</p>}
    <div className="attribute-navigation"><label htmlFor="attribute-jump">Jump to attribute</label><select id="attribute-jump" value="" onChange={(event) => jump(event.target.value)}><option value="">Choose an attribute…</option>{attrs.map((attr) => <option key={attr.id} value={attr.id}>{attr.name}{draft.selections[attr.id]?.length || draft.whitelist[attr.id]?.length ? " · selected" : ""}</option>)}</select><span>{attrs.length} attributes</span></div>
    {attrs.length ? attrs.map((attr) => <AttributeEditor key={attr.id} attr={attr} draft={draft} change={change} query={normalized} catalogAttributes={library?.categories.flatMap(category => category.attributes) || category.attributes} bodyGuide={isV2 && /body/i.test(category.id)} photographic={photographic || attr.thumbnail_mode === "photographic" || attr.thumbnail_kind === "contact_sheet"} open={isOpen(attr)} setOpen={(open) => setOpened((prev) => ({ ...prev, [attr.id]: open }))} />) : <div className="empty-state"><h3>No matching attributes</h3><p>Try another search or category.</p></div>}
  </>;
}
