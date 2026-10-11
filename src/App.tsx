import { useEffect, useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import * as Dialog from "@radix-ui/react-dialog";
import {
  ArrowUpRight,
  Bookmark,
  Check,
  ChevronRight,
  Layers,
  Menu,
  RotateCcw,
  Search,
  Sparkles,
  Trash2,
  X,
} from "./icons";
import {
  api,
  cleanDraft,
  errorMessage,
  matchingValues,
  presetKey,
  readStorage,
  storageKey,
  writeStorage,
} from "./lib";
import { Draft, ImageRecord, Library, emptyDraft } from "./types";
import { LibraryPanel } from "./components/Library";
import { Generator } from "./components/Generator";
import { Gallery } from "./components/Gallery";
import { ImageDetail } from "./components/ImageDetail";
import { ErrorNotice } from "./components/UI";
type Preset = { id: string; name: string; draft: Draft };
function Presets({
  library,
  draft,
  change,
}: {
  library: Library;
  draft: Draft;
  change: (d: Draft) => void;
}) {
  const [presets, setPresets] = useState<Preset[]>(() => {
    const raw = readStorage(presetKey);
    return Array.isArray(raw)
      ? raw
          .filter(
            (p) => p && typeof p.id === "string" && typeof p.name === "string",
          )
          .map((p) => ({
            id: p.id,
            name: p.name,
            draft: cleanDraft(p.draft, library),
          }))
      : [];
  });
  const [name, setName] = useState("");
  const [status, setStatus] = useState("");
  useEffect(() => {
    writeStorage(presetKey, presets);
  }, [presets]);
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <button className="secondary">
          <Bookmark size={15} />
          Presets
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content preset-dialog">
          <Dialog.Title>Your saved directions</Dialog.Title>
          <Dialog.Description>
            Keep selections, allowed variations, and generation settings for
            next time.
          </Dialog.Description>
          <Dialog.Close
            className="icon-button dialog-close"
            aria-label="Close presets"
          >
            <X size={19} />
          </Dialog.Close>
          <form
            className="save-preset"
            onSubmit={(e) => {
              e.preventDefault();
              if (!name.trim()) return;
              setPresets((p) => [
                ...p,
                {
                  id: crypto.randomUUID(),
                  name: name.trim(),
                  draft: structuredClone(draft),
                },
              ]);
              setName("");
              setStatus("Preset saved.");
            }}
          >
            <label htmlFor="preset-name" className="field-label">
              Name this direction
            </label>
            <div>
              <input
                id="preset-name"
                value={name}
                maxLength={80}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Quiet afternoon"
              />
              <button className="primary" disabled={!name.trim()} type="submit">
                Save preset
              </button>
            </div>
          </form>
          <p role="status" className="muted">
            {status}
          </p>
          <div className="preset-list">
            {presets.length ? (
              presets.map((p) => (
                <div key={p.id}>
                  <div>
                    <strong>{p.name}</strong>
                    <p>
                      {Object.keys(p.draft.selections).length} locks ·{" "}
                      {p.draft.mode} · {p.draft.aspect_ratio}
                    </p>
                  </div>
                  <Dialog.Close asChild>
                    <button
                      className="secondary"
                      aria-label={`Apply ${p.name}`}
                      onClick={() => change(cleanDraft(p.draft, library))}
                    >
                      Apply
                      <Check size={14} />
                    </button>
                  </Dialog.Close>
                  <button
                    className="icon-button"
                    aria-label={`Delete ${p.name}`}
                    onClick={() =>
                      setPresets((prev) => prev.filter((x) => x.id !== p.id))
                    }
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              ))
            ) : (
              <p className="muted">
                No presets yet. Save your current composition above.
              </p>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
export default function App() {
  const [library, setLibrary] = useState<Library>();
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
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    api<Library>("/api/library", { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        if (!Array.isArray(data.categories) || !data.categories.length)
          throw new Error("The attribute library is empty.");
        setDraft(cleanDraft(readStorage(storageKey), data));
        setLibrary(data);
        setCategoryId(data.categories[0].id);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorMessage(e));
      });
    return () => controller.abort();
  }, [retry]);
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
                    <Presets
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
                {selected ? (
                  <LibraryPanel
                    key={selected.id}
                    category={selected}
                    draft={draft}
                    change={setDraft}
                    query={categoryOnlyMatch ? "" : query}
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
