import { useEffect, useRef, useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import {
  ArrowUpRight,
  ChevronRight,
  Layers,
  Menu,
  RotateCcw,
  Search,
  Sparkles,
  X,
} from "./icons";
import {
  api,
  ApiError,
  cleanDraft,
  errorMessage,
  matchingValues,
  historyLibrary,
  historicalLibrary,
  presetApplication,
  validComparison,
  validateComparisonAnchor,
  generationDefaults,
  readLegacyPresets,
  readStorage,
  storageKey,
  writeStorage,
} from "./lib";
import { Draft, ImageRecord, Library, ThumbnailStatus, emptyDraft } from "./types";
import { LibraryPanel } from "./components/Library";
import { Generator } from "./components/Generator";
import { Gallery } from "./components/Gallery";
import { ImageDetail } from "./components/ImageDetail";
import { ErrorNotice } from "./components/UI";
import { Presets } from "./components/Presets";
import { ComparisonReview } from "./components/Comparisons";
import { MigrationReview } from "./components/MigrationReview";
function PhotographicProgress({ library }: { library: Library }) {
  const progress = library.thumbnail_progress;
  const attrs = library.categories.flatMap((category) => category.attributes);
  const values = attrs.flatMap(attr => attr.values);
  const sheets = progress?.attribute_completed ?? attrs.filter((attr) => attr.thumbnail_status === "ready" && /^\/preview-atlases\/[a-zA-Z0-9_-]+\.jpg(?:\?v=\d+)?$/.test(attr.thumbnail_url || "")).length;
  const total = progress?.total ?? values.length;
  const completed = progress?.value_completed ?? values.filter(value => value.thumbnail_status === "ready").length;
  const pending = values.filter(value => value.thumbnail_status === "pending").length;
  const swatches = values.filter(value => value.thumbnail_status === "swatch").length;
  const controlOnly = values.filter(value => value.thumbnail_status === "control_only").length;
  const state = progress?.status || "running";
  return <section className="photographic-progress" aria-label="Photographic preview progress">
    <p role="status">Real photo values {completed}/{total} · Contact sheets {sheets}/{attrs.length}<span className="preview-generation-state">{state === "running" ? "Generating" : state === "completed" ? "Completed" : state === "paused" ? "Paused" : "Generation needs attention"}{progress?.failed ? ` · ${progress.failed} failed` : ""}</span></p>
    <progress value={completed} max={total} aria-label="Photographic value preview progress" />
    {library.thumbnail_mode === "mixed" && <p>{pending} pending · {swatches} swatches · {controlOnly} control-only</p>}
    <p>Legacy exploratory samples are independent generations. Provider variability can change subjects and other details. Controlled comparisons require a reviewed baseline, masks, receipts and category publication.</p>
  </section>;
}
export default function App() {
  const [legacyPresets] = useState(readLegacyPresets);
  const [library, setLibrary] = useState<Library>();
  const [historical, setHistorical] = useState<Library>();
  const [versionError, setVersionError] = useState("");
  const [versionRetry, setVersionRetry] = useState(0);
  const [versions, setVersions] = useState<{active_version?: number; legacy_version?: number; library_hash?: string; source_control_mode?: string}>();
  const [catalogRefreshError, setCatalogRefreshError] = useState("");
  const libraryRef = useRef<Library | undefined>(undefined);
  const [anchorError, setAnchorError] = useState('');
  const [draft, setDraft] = useState<Draft>({ ...emptyDraft });
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [categoryId, setCategoryId] = useState("");
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState(() => {
    const workspace = new URLSearchParams(window.location.search).get("workspace");
    return workspace === "gallery" || workspace === "comparisons" ? workspace : "studio";
  });
  const [mobileNav, setMobileNav] = useState(false);
  const [reviewVisited, setReviewVisited] = useState(tab === "comparisons");
  const [image, setImage] = useState<ImageRecord | null>(null);
  const [galleryRevision, setGalleryRevision] = useState(0);
  const [reuseUndo, setReuseUndo] = useState<Draft>();
  const [thumbnailError, setThumbnailError] = useState(false);
  const [thumbnailRetry, setThumbnailRetry] = useState(0);
  const [migrationSource, setMigrationSource] = useState<{name: string; draft: Record<string, unknown>; schemaVersion?: number} | null>(null);
  const [storedArchive, setStoredArchive] = useState<Record<string, unknown> | null>(null);
  const [migrationPurpose, setMigrationPurpose] = useState<"reuse" | "restore">("reuse");
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    api<Library>("/api/library", { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        if (!Array.isArray(data.categories) || !data.categories.length)
          throw new Error("The attribute library is empty.");
        const raw = readStorage(storageKey);
        const restored = cleanDraft(raw, data);
        if (restored.comparison) {
          void validateComparisonAnchor(restored.comparison, data).then(valid => {
            if (controller.signal.aborted) return;
            if (valid) setDraft(restored);
            else { const {comparison: _anchor, ...rest} = restored; setDraft(rest); setAnchorError('Stored comparison metadata is stale or unavailable. Review the current group before reapplying it.'); }
          });
        } else setDraft(restored);
        if (raw && typeof raw === "object" && !Array.isArray(raw) && presetApplication(raw as Record<string, unknown>, data).unresolved.length) {
          setStoredArchive(raw as Record<string, unknown>);
        }
        libraryRef.current = data;
        setLibrary(data);
        setCategoryId(data.categories[0].id);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorMessage(e));
      });
    return () => controller.abort();
  }, [retry]);
  const libraryLoaded = !!library;
  useEffect(() => {
    if (!libraryLoaded) return;
    const controller = new AbortController();
    setVersionError("");
    api<{ active_version?: number; legacy_version?: number; library_hash?: string; source_control_mode?: string; library?: Library; legacy_library?: Library; historical_library?: Library }>("/api/catalog/versions", {signal: controller.signal})
      .then(versions => {
        if (controller.signal.aborted || !libraryRef.current) return;
        const legacy = versions.historical_library || versions.legacy_library;
        if (legacy && !Array.isArray(legacy.categories)) throw new Error("Invalid historical catalog vocabulary.");
        setHistorical(legacy ? historicalLibrary(libraryRef.current, legacy) : historyLibrary(libraryRef.current));
        setVersions(versions);
      })
      .catch(e => {
        if (controller.signal.aborted) return;
        if (!(e instanceof ApiError && e.status === 404)) setVersionError(errorMessage(e));
      });
    return () => controller.abort();
  }, [libraryLoaded, versionRetry]);
  useEffect(() => {
    if (!libraryLoaded) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let observedVersion = libraryRef.current?.thumbnail_progress?.version;
    async function poll() {
      let delay = 10_000;
      try {
        const status = await api<ThumbnailStatus>("/api/thumbnail-status", { signal: controller.signal, cache: "no-store" });
        if (controller.signal.aborted) return;
        if (!Number.isInteger(status.version) || status.version < 0) throw new Error("Invalid preview status");
        const current = libraryRef.current!;
        const mode = status.mode || (status.status ? "photographic" : "illustrative");
        if (status.version !== observedVersion || (current.thumbnail_mode !== "mixed" && mode !== (current.thumbnail_mode || "illustrative"))) {
          const data = await api<Library>("/api/library", { signal: controller.signal, cache: "no-store" });
          if (controller.signal.aborted) return;
          if (!Array.isArray(data.categories) || !data.categories.length) throw new Error("Empty preview library");
          // Preview refreshes replace only the library; the user's draft and navigation stay in place.
          const next = { ...data, thumbnail_mode: data.thumbnail_mode || mode, thumbnail_progress: mode === "photographic" ? status : undefined };
          libraryRef.current = next;
          setLibrary(next);
        } else if (mode === "photographic") {
          const next = { ...current, thumbnail_progress: status };
          libraryRef.current = next;
          setLibrary(next);
        }
        observedVersion = status.version;
        setThumbnailError(false);
        delay = mode === "photographic" && status.status === "running" ? 10_000 : 60_000;
      } catch (e) {
        if (controller.signal.aborted) return;
        // Older servers and illustrative fixtures have no status endpoint.
        if (e instanceof ApiError && e.status === 404 && libraryRef.current?.thumbnail_mode !== "photographic") return;
        setThumbnailError(true);
        delay = libraryRef.current?.thumbnail_progress?.status === "running" ? 10_000 : 60_000;
      }
      if (!controller.signal.aborted) timer = setTimeout(poll, delay);
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [libraryLoaded, thumbnailRetry]);
  useEffect(() => {
    if (library && !storedArchive) writeStorage(storageKey, draft);
  }, [draft, library, storedArchive]);
  async function applyReviewedDraft(next: Draft): Promise<boolean> {
    if (!library) return false;
    if (next.comparison && !await validateComparisonAnchor(next.comparison, library)) {
      setAnchorError('Saved comparison metadata is stale or unavailable. Review its current group baseline before applying this preset.');
      return false;
    }
    setAnchorError(''); setDraft(next); return true;
  }
  function showImage(i: ImageRecord) {
    document
      .querySelectorAll("[data-detail-origin]")
      .forEach((el) => el.removeAttribute("data-detail-origin"));
    document.activeElement?.setAttribute("data-detail-origin", "true");
    setImage(i);
  }
  async function refreshCatalog() {
    setCatalogRefreshError("");
    try {
      const data = await api<Library>("/api/library", {cache: "no-store"});
      if (!Array.isArray(data.categories) || !data.categories.length) throw new Error("The attribute library is empty.");
      libraryRef.current = data;
      setLibrary(data);
      setHistorical(historyLibrary(data));
    } catch (e) { setCatalogRefreshError(errorMessage(e)); }
  }
  function changeTab(value: string) {
    if (value === "comparisons") setReviewVisited(true);
    setTab(value);
    const url = new URL(window.location.href);
    if (value !== "studio") url.searchParams.set("workspace", value); else url.searchParams.delete("workspace");
    window.history.replaceState(null, "", url);
  }
  const normalized = query.trim().toLowerCase();
  function matchCount(category: Library["categories"][number]) {
    return category.name.toLowerCase().includes(normalized)
      ? category.attributes.reduce((n, attr) => n + attr.values.length, 0)
      : category.attributes.reduce((n, attr) => n + matchingValues(attr, normalized).length, 0);
  }
  function editAttribute(id: string) {
    const category = library?.categories.find((c) => c.attributes.some((a) => a.id === id));
    if (!category) return;
    setCategoryId(category.id);
    setQuery("");
    requestAnimationFrame(() => {
      const heading = document.querySelector<HTMLButtonElement>(`#attribute-${CSS.escape(id)} .attribute-toggle`);
      if (heading?.getAttribute("aria-expanded") === "false") heading.click();
      heading?.scrollIntoView({ block: "start" });
      heading?.focus({ preventScroll: true });
    });
  }
  const matchingCategories =
    library?.categories.filter(
      (c) =>
        !normalized ||
        c.name.toLowerCase().includes(normalized) ||
        c.attributes.some((a) => draft.selections[a.id]?.length || draft.whitelist[a.id]?.length) || c.attributes.some(
          (a) =>
            `${a.name} ${a.description || ""}`
              .toLowerCase()
              .includes(normalized) ||
            a.values.some((v) =>
              `${v.name} ${v.description || ""} ${v.steers}`
                .toLowerCase()
                .includes(normalized),
            ),
        ),
    ) || [];
  const selected =
    matchingCategories.find((c) => c.id === categoryId) ||
    matchingCategories[0];
  const categoryOnlyMatch = selected?.name.toLowerCase().includes(normalized);
  return (
    <>
      <a
        href={
          !library
            ? "#startup"
            : tab === "studio"
              ? "#studio-content"
              : tab === "comparisons" ? "#comparisons-content" : "#gallery-content"
        }
        className="skip-link"
      >
        Skip to content
      </a>
      <Tabs.Root value={tab} onValueChange={changeTab} className="app">
        <header className="topbar">
          <a className="brand" href="/" aria-label="Atelier home">
            <span className="brand-icon">
              <Layers size={23} strokeWidth={1.3} />
            </span>
            <span>
              atelier<span className="brand-dot">.</span>
            </span>
          </a>
          <Tabs.List aria-label="Workspace" className="workspace-tabs">
            <Tabs.Trigger value="studio">
              <Sparkles size={15} />
              Studio
            </Tabs.Trigger>
            <Tabs.Trigger value="gallery">
              <Layers size={15} />
              Gallery
            </Tabs.Trigger>
            <Tabs.Trigger value="comparisons">Category review</Tabs.Trigger>
          </Tabs.List>
          <span className="topbar-note">
            <span />
            IMAGE STUDIO
          </span>
        </header>
        {error ? (
          <main id="startup" tabIndex={-1} className="startup">
            <ErrorNotice
              message={`Library unavailable: ${error}`}
              retry={() => setRetry((v) => v + 1)}
            />
          </main>
        ) : !library ? (
          <main id="startup" tabIndex={-1} className="startup" aria-busy="true">
            <Layers size={30} />
            <h1>Opening the studio…</h1>
            <p role="status">Loading the attribute library.</p>
          </main>
        ) : (
          <>
            <main aria-label="Creative workspace">
            {catalogRefreshError && <ErrorNotice message={`Publication succeeded, but updated catalog previews could not be loaded: ${catalogRefreshError}`} retry={() => { void refreshCatalog(); }} />}
            <Tabs.Content forceMount value="studio" tabIndex={-1} className="studio">
              <aside
                className={`sidebar ${mobileNav ? "mobile-open" : ""}`}
                aria-label="Attribute categories"
                id="library-categories"
              >
                <div className="sidebar-heading">
                  <span className="eyebrow">CREATIVE TOOLKIT</span>
                  <button
                    className="icon-button mobile-only"
                    aria-label="Close category menu"
                    onClick={() => setMobileNav(false)}
                  >
                    <X size={18} />
                  </button>
                </div>
                <label className="search-field">
                  <Search size={16} />
                  <input
                    aria-label="Search library"
                    value={query}
                    onChange={(e) => {
                      const next = e.target.value.trim().toLowerCase();
                      setQuery(e.target.value);
                      const matches = library.categories.filter((c) => c.name.toLowerCase().includes(next) || c.attributes.some((a) => matchingValues(a, next).length));
                      if (!matches.some((c) => c.id === categoryId) && matches[0]) setCategoryId(matches[0].id);
                    }}
                    placeholder="Search the library"
                  />
                </label>
                <nav aria-label="Library categories">
                  {matchingCategories.map((c, i) => (
                    <button
                      key={c.id}
                      aria-current={selected?.id === c.id ? "page" : undefined}
                      onClick={() => {
                        setCategoryId(c.id);
                        setMobileNav(false);
                      }}
                    >
                      <span className="category-number">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span>{c.name}</span>
                      {normalized && <span role="status" className="category-match-count" aria-label={`${matchCount(c)} matching values`}>{matchCount(c)}</span>}
                      <ChevronRight size={14} />
                    </button>
                  ))}
                </nav>
                {!matchingCategories.length && (
                  <p className="muted">No categories match.</p>
                )}
                <div className="sidebar-bottom">
                  <span className="eyebrow">
                    A LITTLE STRUCTURE.
                    <br />
                    ENDLESS POSSIBILITY.
                  </span>
                  <p>
                    Every detail is a decision.
                    <br />
                    Start with the ones that matter.
                  </p>
                  <ArrowUpRight size={20} />
                </div>
              </aside>
              <div id="studio-content" tabIndex={-1} className="library-main">
                <button
                  className="secondary mobile-only"
                  aria-expanded={mobileNav}
                  aria-controls="library-categories"
                  onClick={() => setMobileNav(true)}
                >
                  <Menu size={16} />
                  Browse categories
                </button>
                <button className="secondary mobile-only" onClick={() => { const target = document.getElementById('composition'); target?.scrollIntoView({ behavior: 'smooth', block: 'start' }); target?.focus({ preventScroll: true }); }}>Go to composition</button>
                <div className="hero">
                  <span className="eyebrow">COMPOSE · EXPLORE · CREATE</span>
                  <h1>
                    A vision, <em>in the details.</em>
                  </h1>
                  <p>
                    Build a visual direction, one thoughtful choice at a time.
                  </p>
                  <p className="catalog-census" aria-label="Catalog counts">{library.categories.length} categories · {library.categories.reduce((n, c) => n + c.attributes.length, 0)} attributes · {library.categories.reduce((n, c) => n + c.attributes.reduce((total, a) => total + a.values.length, 0), 0)} values{versions?.active_version ? ` · Active v${versions.active_version}` : ""}{versions?.legacy_version ? ` · Archived v${versions.legacy_version}` : ""}</p>
                  <div className="hero-actions">
                    <Presets legacy={legacyPresets}
                      library={library}
                      draft={draft}
                      change={next => { void applyReviewedDraft(next); }}
                    />
                    <button
                      className="text-button"
                      onClick={() => { setDraft(cleanDraft(null, library)); setReuseUndo(undefined); }}
                    >
                      <RotateCcw size={14} />
                      Reset composition
                    </button>
                  </div>
                  {reuseUndo && <div className="reuse-notice" role="status">Image selections loaded. Your previous composition is saved for undo. <button className="text-button" onClick={() => { setDraft(reuseUndo); setReuseUndo(undefined); }}>Undo reuse</button></div>}
                  {storedArchive && <div className="reuse-notice" role="status">Your stored composition contains archived or unsupported controls. Its original cache is retained until you apply a migration.<button className="text-button" onClick={() => { setMigrationPurpose("restore"); setMigrationSource({name: "Stored composition", draft: storedArchive}); }}>Review stored composition</button></div>}
                  {anchorError && <ErrorNotice message={anchorError} />}
                  {draft.comparison && <div className="reuse-notice" role="status">Preset anchor: {draft.comparison.category_id} · {draft.comparison.locked_fields.length} reviewed comparison fields. Reference metadata only; not applied to generation.<button className="text-button" onClick={() => { const {comparison: _anchor, ...rest} = draft; setDraft(rest); }}>Remove preset anchor</button></div>}
                  <div className="hero-decoration" aria-hidden="true">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
                {(library.thumbnail_mode === "photographic" || library.thumbnail_mode === "mixed") && <PhotographicProgress library={library} />}
                {thumbnailError && <div className="preview-update-notice" role="status"><span>Preview updates are temporarily unavailable. You can keep composing.</span><button className="text-button" onClick={() => setThumbnailRetry((value) => value + 1)}>Reload previews</button></div>}
                {selected ? (
                  <LibraryPanel
                    key={selected.id}
                    library={library}
                    category={selected}
                    draft={draft}
                    change={setDraft}
                    query={categoryOnlyMatch ? "" : query}
                    photographic={library.thumbnail_mode === "photographic" || library.thumbnail_mode === "mixed"}
                  />
                ) : (
                  <div className="empty-state">
                    <h2>No matching library entries</h2>
                    <button className="secondary" onClick={() => setQuery("")}>
                      Clear search
                    </button>
                  </div>
                )}
              </div>
              {generationDefaults(draft, library).length > 0 && <p role="note">Generation defaults for unset controls: {generationDefaults(draft, library).join('; ')}. These are applied by the server, including when you add free text.</p>}
              <Generator
                library={library}
                draft={draft}
                change={setDraft}
                onImage={showImage}
                onComplete={() => setGalleryRevision((v) => v + 1)}
                onEditAttribute={editAttribute}
              />
            </Tabs.Content>
            <Tabs.Content
              forceMount
              value="gallery"
              tabIndex={-1}
              className="gallery-main"
            >
              <div id="gallery-content" tabIndex={-1}>{tab === "gallery" && <Gallery
                library={library}
                historicalLibrary={historical || historyLibrary(library)}
                revision={galleryRevision}
                onImage={showImage}
              />}</div>
              {versionError && <ErrorNotice message={`Historical catalog unavailable: ${versionError}`} retry={() => setVersionRetry(v => v + 1)} />}
            </Tabs.Content>
            <Tabs.Content forceMount value="comparisons" tabIndex={-1} className="comparisons-main">
              <div id="comparisons-content" tabIndex={-1}>{reviewVisited && <ComparisonReview library={library} onPublished={() => { void refreshCatalog(); }} onSelectAnchor={anchor => {
                if (validComparison(anchor, library)) void applyReviewedDraft({...draft, comparison: anchor});
              }} />}</div>
            </Tabs.Content>
            </main>
            <ImageDetail
              image={image}
              library={historical || historyLibrary(library)}
              close={() => setImage(null)}
              reuse={(i) => {
                setMigrationPurpose("reuse");
                const seed = i.selection_sampling_seed ?? i.seed;
                setMigrationSource({name: "Image selections", draft: {...emptyDraft, selections: i.selections, aspect_ratio: i.aspect_ratio, ...(seed === undefined || seed === null ? {} : {seed})}});
                setImage(null);
              }}
            />
            <MigrationReview source={migrationSource} library={library} onCancel={() => setMigrationSource(null)} onApply={async next => {
              if (!await applyReviewedDraft(next)) { setMigrationSource(null); changeTab('studio'); return; }
              setReuseUndo(structuredClone(draft));
              if (migrationPurpose === "restore") setStoredArchive(null);
              setMigrationSource(null);
              changeTab("studio");
              setQuery("");
            }} />
          </>
        )}
      </Tabs.Root>
      <footer className="site-footer">
        <span>ATELIER / IMAGE STUDIO</span>
        <span>Space for your next idea.</span>
      </footer>
    </>
  );
}
