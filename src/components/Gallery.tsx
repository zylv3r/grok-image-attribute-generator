import { useEffect, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import {
  ArrowLeft,
  ArrowRight,
  Search,
  SlidersHorizontal,
  X,
  Images,
} from "../icons";
import { api, errorMessage, attributes, matchingValues, imageDescription, galleryState, historyLibrary } from "../lib";
import {
  Attribute,
  Choices,
  GalleryResponse,
  ImageRecord,
  Library,
  ratios,
} from "../types";
import { CheckControl, ErrorNotice, Picker, Thumb } from "./UI";
export function archivedGalleryState(search: string, library: Library) {
  const state = galleryState(search, library);
  // Vocabulary may arrive after the active library. Keep bounded historical IDs in
  // the URL and query while it loads, so archive filters never disappear silently.
  try {
    const raw: unknown = JSON.parse(new URLSearchParams(search).get("gallery_filters") || "{}");
    if (raw && typeof raw === "object" && !Array.isArray(raw)) {
      const entries = Object.entries(raw).slice(0, 256).flatMap(([id, values]) => {
        if (!/^[a-zA-Z0-9_-]{1,80}$/.test(id) || !Array.isArray(values)) return [];
        const ids = [...new Set(values.slice(0, 512).filter((value): value is string => typeof value === "string" && value.length > 0 && value.length <= 200))];
        return ids.length ? [[id, ids] as const] : [];
      });
      state.filters = Object.fromEntries(entries);
    }
  } catch { /* Invalid URL JSON does not prevent opening the collection. */ }
  return state;
}
function FilterAttribute({ attr, activeAttr, query, ids, toggle, initialOpen }: {
  attr: Attribute; activeAttr?: Attribute; query: string; ids: string[]; toggle: (id: string, checked: boolean) => void; initialOpen: boolean;
}) {
  const [limit, setLimit] = useState(12);
  const [previousQuery, setPreviousQuery] = useState(query);
  if (previousQuery !== query) { setPreviousQuery(query); setLimit(12); }
  const matches = matchingValues(attr, query);
  const values = attr.values.filter((v) => matches.includes(v) || ids.includes(v.id));
  if (!values.length) return null;
  const shown = values.filter((v, index) => index < limit || ids.includes(v.id));
  return <details className="filter-attribute" open={!!query || initialOpen || ids.length > 0}>
    <summary>{attr.name}{!activeAttr && " · Archived"} <span>{values.length} values{ids.length ? ` · ${ids.length} selected` : ""}</span></summary>
    {!activeAttr && <p className="field-help">Archived control. Available for historical filtering; generation requires catalog migration.</p>}
    <fieldset><legend>{attr.name}</legend>{shown.map((v) => <CheckControl key={v.id} label={`${attr.name}: ${v.name}${!activeAttr?.values.some(value => value.id === v.id) ? " · Archived" : ""}`} checked={ids.includes(v.id)} onChange={(checked) => toggle(v.id, checked)} />)}</fieldset>
    {values.length > shown.length && <button className="text-button" onClick={() => setLimit((n) => n + 12)}>Show more {attr.name} filters ({values.length - shown.length} remaining)</button>}
  </details>;
}
export function Gallery({
  library,
  historicalLibrary,
  revision,
  onImage,
}: {
  library: Library;
  historicalLibrary?: Library;
  revision: number;
  onImage: (image: ImageRecord) => void;
}) {
  const archiveLibrary = historicalLibrary || historyLibrary(library);
  const activeAttrs = attributes(library);
  const [initial] = useState(() => archivedGalleryState(window.location.search, archiveLibrary));
  const [query, setQuery] = useState(initial.query);
  const [ratio, setRatio] = useState(initial.ratio);
  const [filters, setFilters] = useState<Choices>(initial.filters);
  const [filterQuery, setFilterQuery] = useState("");
  const [page, setPage] = useState(initial.page);
  const [response, setResponse] = useState<GalleryResponse>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const first = useRef(true);
  useEffect(() => {
    const url = new URL(window.location.href);
    const values = { gallery_q: query, gallery_ratio: ratio === "all" ? "" : ratio, gallery_filters: Object.keys(filters).length ? JSON.stringify(filters) : "", gallery_page: page > 1 ? String(page) : "" };
    for (const [key, value] of Object.entries(values)) { if (value) url.searchParams.set(key, value); else url.searchParams.delete(key); }
    window.history.replaceState(null, "", url);
  }, [query, ratio, filters, page]);
  useEffect(() => {
    function restore() {
      const next = archivedGalleryState(window.location.search, archiveLibrary);
      setQuery(next.query); setRatio(next.ratio); setFilters(next.filters); setPage(next.page);
    }
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, [archiveLibrary]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    const timer = setTimeout(
      async () => {
        const params = new URLSearchParams({
          q: query,
          page: String(page),
          page_size: "24",
          filters: JSON.stringify(filters),
        });
        if (ratio !== "all") params.set("aspect_ratio", ratio);
        try {
          const data = await api<GalleryResponse>(`/api/gallery?${params}`, {
            signal: controller.signal,
          });
          if (!controller.signal.aborted) {
            if (page > 1 && page > data.pages) {
              setPage(Math.max(1, data.pages));
              return;
            }
            setResponse(data);
            setLoading(false);
          }
        } catch (e) {
          if (!controller.signal.aborted) {
            setError(errorMessage(e));
            setLoading(false);
          }
        }
      },
      first.current ? 0 : 300,
    );
    first.current = false;
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [query, ratio, filters, page, retry, revision]);
  function toggle(attr: string, id: string, checked: boolean) {
    setPage(1);
    setFilters((prev) => {
      const next = { ...prev };
      const ids = checked
        ? [...(prev[attr] || []), id]
        : (prev[attr] || []).filter((v) => v !== id);
      if (ids.length) next[attr] = ids;
      else delete next[attr];
      return next;
    });
  }
  const filterCount = Object.values(filters).reduce(
    (n, ids) => n + ids.length,
    0,
  );
  return (
    <div className="gallery">
      <div className="gallery-heading">
        <div>
          <span className="eyebrow">THE COLLECTION</span>
          <h1>Your image archive.</h1>
          <p>A record of every direction you’ve explored.</p>
        </div>
        <Images size={38} strokeWidth={1} />
      </div>
      <div className="gallery-toolbar">
        <label className="search-field">
          <Search size={17} />
          <input
            aria-label="Search gallery"
            maxLength={500}
            placeholder="Search prompts…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
          />
        </label>
        <Picker
          label="Gallery aspect ratio"
          value={ratio}
          onChange={(v) => {
            setRatio(v);
            setPage(1);
          }}
          options={[
            { value: "all", label: "All ratios" },
            ...ratios.map((value) => ({ value, label: value })),
          ]}
        />
        <Dialog.Root>
          <Dialog.Trigger asChild>
            <button className="secondary">
              <SlidersHorizontal size={15} />
              Attribute filters
              {filterCount > 0 && (
                <span className="count-badge">{filterCount}</span>
              )}
            </button>
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="dialog-overlay" />
            <Dialog.Content className="dialog-content filter-dialog">
              <Dialog.Title>Filter the archive</Dialog.Title>
              <Dialog.Description>
                Match all selected attributes. Within each attribute, match any
                checked value. Unset means no instruction, not off. Attribute filters exclude untagged images. Archived controls remain searchable here and do not change generation controls.
              </Dialog.Description>
              <Dialog.Close
                className="icon-button dialog-close"
                aria-label="Close filters"
              >
                <X size={19} />
              </Dialog.Close>
              <label className="search-field">
                <Search size={16} />
                <input
                  aria-label="Search filter values"
                  value={filterQuery}
                  onChange={(e) => setFilterQuery(e.target.value)}
                  placeholder="Find any attribute or value…"
                />
              </label>
              <div className="filter-list">
                {archiveLibrary.categories.map((category, categoryIndex) => {
                  const normalized = filterQuery.trim().toLowerCase();
                  const query = category.name.toLowerCase().includes(normalized) ? "" : normalized;
                  const attrs = category.attributes.filter((attr) => matchingValues(attr, query).length || filters[attr.id]?.length);
                  return attrs.length ? <section key={category.id}><h3>{category.name}{category.retired || !library.categories.some(active => active.id === category.id) ? " · Archived" : ""}</h3>{attrs.map((attr, index) => <FilterAttribute key={attr.id} attr={attr} activeAttr={activeAttrs.find(active => active.id === attr.id)} query={query} ids={filters[attr.id] || []} initialOpen={categoryIndex === 0 && index < 2} toggle={(id, checked) => toggle(attr.id, id, checked)} />)}</section> : null;
                })}
              </div>
              <div className="dialog-actions">
                <button
                  className="secondary"
                  onClick={() => {
                    setFilters({});
                    setPage(1);
                  }}
                >
                  Clear filters
                </button>
                <Dialog.Close asChild>
                  <button className="primary">Show matching images</button>
                </Dialog.Close>
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </div>
      {filterCount > 0 && (
        <div className="active-filters">
          {Object.entries(filters).flatMap(([id, ids]) => {
            const attr = attributes(archiveLibrary).find((a) => a.id === id);
            return ids.map((value) => { const archived = !activeAttrs.find(active => active.id === id)?.values.some(item => item.id === value); const label = `${attr?.name || id}: ${attr?.values.find((v) => v.id === value)?.name || value}${archived ? " · Archived" : ""}`; return <button className="filter-chip" key={`${id}-${value}`} aria-label={`Remove filter ${label}`} onClick={() => toggle(id, value, false)}>{label}<X size={12} aria-hidden="true" /></button>; });
          })}
          <button
            className="text-button"
            onClick={() => {
              setFilters({});
              setPage(1);
            }}
          >
            Clear all
          </button>
        </div>
      )}
      {filterCount > 0 && <p className="field-help">Attribute filters exclude untagged images. Unset is no recorded instruction; it is not an explicit off value.</p>}
      <div className="gallery-count" role="status">
        {loading
          ? "Loading collection…"
          : error
            ? "Collection unavailable"
            : `${response?.total || 0} images · 24 per page`}
      </div>
      {error ? (
        <ErrorNotice message={error} retry={() => setRetry((v) => v + 1)} />
      ) : loading ? (
        <div
          className="gallery-grid"
          aria-label="Loading images"
          aria-busy="true"
        >
          {Array.from({ length: 6 }, (_, i) => (
            <div className="skeleton gallery-skeleton" key={i} />
          ))}
        </div>
      ) : response?.items.length ? (
        <>
          <div className="gallery-grid">
            {response.items.map((image, i) => (
              <button
                className="gallery-card"
                key={image.id}
                onClick={() => onImage(image)}
                aria-label={`Open image ${image.id}`}
              >
                <Thumb url={image.thumbnail_url || image.url} name="Image" alt={imageDescription(image, archiveLibrary)} />
                <div>
                  <span>
                    No. {String((page - 1) * 24 + i + 1).padStart(3, "0")}
                  </span>
                  <span>{image.aspect_ratio}</span>
                </div>
                <p>{image.prompt}</p>
              </button>
            ))}
          </div>
          <nav className="pagination" aria-label="Gallery pagination">
            <button
              className="secondary"
              disabled={page <= 1 || loading}
              onClick={() => setPage((p) => p - 1)}
            >
              <ArrowLeft size={15} />
              Previous
            </button>
            <span>
              Page {response.page} of {response.pages}
            </span>
            <button
              className="secondary"
              disabled={page >= response.pages || loading}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
              <ArrowRight size={15} />
            </button>
          </nav>
        </>
      ) : (
        <div className="empty-state">
          <Images size={42} strokeWidth={1} />
          <h2>
            {query || filterCount || ratio !== "all"
              ? "No images match your filters."
              : "A blank canvas, for now."}
          </h2>
          <p>
            {query || filterCount || ratio !== "all"
              ? "Try a broader search or clear your filters."
              : "Create your first composition in the Studio. It will find a home here."}
          </p>
          {(query || filterCount || ratio !== "all") && (
            <button
              className="secondary"
              onClick={() => {
                setQuery("");
                setRatio("all");
                setFilters({});
                setPage(1);
              }}
            >
              Clear search & filters
            </button>
          )}
        </div>
      )}
    </div>
  );
}
