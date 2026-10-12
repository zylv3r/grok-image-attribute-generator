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
function PhotographicProgress({ library }: { library: Library }) {
  const progress = library.thumbnail_progress;
  const attrs = library.categories.flatMap((category) => category.attributes);
  const sheets = progress?.attribute_completed ?? attrs.filter((attr) => attr.thumbnail_status === "ready" && /^\/preview-atlases\/[a-zA-Z0-9_-]+\.jpg$/.test(attr.thumbnail_url || "")).length;
  const total = progress?.total ?? 893;
  const completed = progress?.value_completed ?? 0;
  const state = progress?.status || "running";
  return <section className="photographic-progress" aria-label="Photographic preview progress">
    <p role="status">Real photo values {completed}/{total} · Contact sheets {sheets}/{attrs.length}<span className="preview-generation-state">{state === "running" ? "Generating" : state === "completed" ? "Completed" : state === "paused" ? "Paused" : "Generation needs attention"}{progress?.failed ? ` · ${progress.failed} failed` : ""}</span></p>
    <progress value={completed} max={total} aria-label="Photographic value preview progress" />
    <p>Within each attribute, examples use a fixed photographic prompt baseline; only the target value steer changes. Provider variability can change the subject and other details between examples. Generated examples are searchable in Gallery.</p>
  </section>;
}
export default function App() {
  const [legacyPresets] = useState(readLegacyPresets);
  const [library, setLibrary] = useState<Library>();
  const libraryRef = useRef<Library | undefined>(undefined);
  const [draft, setDraft] = useState<Draft>({ ...emptyDraft });
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [categoryId, setCategoryId] = useState("");
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState(() => new URLSearchParams(window.location.search).get("workspace") === "gallery" ? "gallery" : "studio");
  const [mobileNav, setMobileNav] = useState(false);
  const [image, setImage] = useState<ImageRecord | null>(null);
  const [galleryRevision, setGalleryRevision] = useState(0);
  const [reuseUndo, setReuseUndo] = useState<Draft>();
  const [thumbnailError, setThumbnailError] = useState(false);
  const [thumbnailRetry, setThumbnailRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    api<Library>("/api/library", { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        if (!Array.isArray(data.categories) || !data.categories.length)
          throw new Error("The attribute library is empty.");
        setDraft(cleanDraft(readStorage(storageKey), data));
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
        if (status.version !== observedVersion || mode !== (current.thumbnail_mode || "illustrative")) {
          const data = await api<Library>("/api/library", { signal: controller.signal, cache: "no-store" });
          if (controller.signal.aborted) return;
          if (!Array.isArray(data.categories) || !data.categories.length) throw new Error("Empty preview library");
          // Preview refreshes replace only the library; the user's draft and navigation stay in place.
          const next = { ...data, thumbnail_mode: mode, thumbnail_progress: mode === "photographic" ? status : undefined };
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
    if (library) writeStorage(storageKey, draft);
  }, [draft, library]);
  function showImage(i: ImageRecord) {
    document
      .querySelectorAll("[data-detail-origin]")
      .forEach((el) => el.removeAttribute("data-detail-origin"));
    document.activeElement?.setAttribute("data-detail-origin", "true");
    setImage(i);
  }
  function changeTab(value: string) {
    setTab(value);
    const url = new URL(window.location.href);
    if (value === "gallery") url.searchParams.set("workspace", "gallery"); else url.searchParams.delete("workspace");
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
              : "#gallery-content"
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
                  <div className="hero-actions">
                    <Presets legacy={legacyPresets}
                      library={library}
                      draft={draft}
                      change={setDraft}
                    />
                    <button
                      className="text-button"
                      onClick={() => { setDraft({ ...emptyDraft }); setReuseUndo(undefined); }}
                    >
                      <RotateCcw size={14} />
                      Reset composition
                    </button>
                  </div>
                  {reuseUndo && <div className="reuse-notice" role="status">Image selections loaded. Your previous composition is saved for undo. <button className="text-button" onClick={() => { setDraft(reuseUndo); setReuseUndo(undefined); }}>Undo reuse</button></div>}
                  <div className="hero-decoration" aria-hidden="true">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
                {library.thumbnail_mode === "photographic" && <PhotographicProgress library={library} />}
                {thumbnailError && <div className="preview-update-notice" role="status"><span>Preview updates are temporarily unavailable. You can keep composing.</span><button className="text-button" onClick={() => setThumbnailRetry((value) => value + 1)}>Reload previews</button></div>}
                {selected ? (
                  <LibraryPanel
                    key={selected.id}
                    category={selected}
                    draft={draft}
                    change={setDraft}
                    query={categoryOnlyMatch ? "" : query}
                    photographic={library.thumbnail_mode === "photographic"}
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
                revision={galleryRevision}
                onImage={showImage}
              />}</div>
            </Tabs.Content>
            </main>
            <ImageDetail
              image={image}
              library={library}
              close={() => setImage(null)}
              reuse={(i) => {
                setReuseUndo(structuredClone(draft));
                setDraft(
                  cleanDraft(
                    {
                      ...emptyDraft,
                      selections: i.selections,
                      aspect_ratio: i.aspect_ratio,
                      seed: i.selection_sampling_seed ?? i.seed,
                    },
                    library,
                  ),
                );
                changeTab("studio");
                setQuery("");
                setImage(null);
              }}
            />
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
