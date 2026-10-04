"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { api, ApiClientError, type CaseCard } from "@/lib/api";
import { CONFIDENCE_META, VERDICT_META } from "@/lib/presentation";

const VERDICT_FILTERS = [
  { value: "", label: "All verdicts" },
  { value: "LIKELY_DERIVED", label: "Likely derived" },
  { value: "HEAVILY_DERIVED", label: "Heavily derived" },
  { value: "SHARED_UPSTREAM", label: "Shared upstream" },
  { value: "INDEPENDENT", label: "Independent" },
  { value: "DECLARED_FORK", label: "Declared fork" },
  { value: "INSUFFICIENT_EVIDENCE", label: "Insufficient evidence" },
];

const PAGE_SIZE = 12;

/**
 * Explore: the public case registry.
 *
 * Handles three states honestly, because an empty registry is the normal case
 * for a new deployment: loading, empty, and populated.
 */
export function ExploreView() {
  const [query, setQuery] = useState("");
  const [verdict, setVerdict] = useState("");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<CaseCard[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (nextOffset: number, q: string, v: string) => {
      setLoading(true);
      setError(null);
      try {
        const result = q || v
          ? await api.search({ q, verdict: v || undefined, limit: PAGE_SIZE, offset: nextOffset })
          : await api.listCases({ limit: PAGE_SIZE, offset: nextOffset });
        setItems(result.items);
        setTotal(result.total);
        setHasMore(result.has_more);
      } catch (err) {
        setError(
          err instanceof ApiClientError
            ? err.message
            : "Cases could not be loaded. The analysis service may be unavailable.",
        );
        setItems([]);
        setTotal(0);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    void load(offset, query, verdict);
  }, [load, offset, query, verdict]);

  // Debounce the search field so typing does not fire a request per keystroke.
  useEffect(() => {
    const id = window.setTimeout(() => setOffset(0), 250);
    return () => window.clearTimeout(id);
  }, [query, verdict]);

  return (
    <div className="layout explore-page">
      <header className="explore-head">
        <div>
          <p className="eyebrow">Public registry</p>
          <h1 className="heading-1">Explore cases</h1>
          <p className="lead">
            Every case is public and permanently addressable. Open one to inspect
            its evidence, its counter-evidence, and every competing explanation
            that was weighed.
          </p>
        </div>

        <form
          className="explore-controls"
          role="search"
          onSubmit={(event) => {
            event.preventDefault();
            setOffset(0);
          }}
        >
          <div className="explore-search">
            <label htmlFor="explore-q" className="sr-only">
              Search cases by repository
            </label>
            <input
              id="explore-q"
              type="search"
              className="explore-input"
              placeholder="Search by repository or case id…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>

          <div className="explore-filter">
            <label htmlFor="explore-verdict" className="sr-only">
              Filter by verdict
            </label>
            <select
              id="explore-verdict"
              className="explore-select"
              value={verdict}
              onChange={(event) => setVerdict(event.target.value)}
            >
              {VERDICT_FILTERS.map((filter) => (
                <option key={filter.value} value={filter.value}>
                  {filter.label}
                </option>
              ))}
            </select>
          </div>
        </form>
      </header>

      {error ? (
        <div className="explore-error" role="alert">
          <p>{error}</p>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => void load(offset, query, verdict)}
          >
            Retry
          </button>
        </div>
      ) : null}

      {!error && loading && items.length === 0 ? (
        <ul className="case-grid" aria-busy="true">
          {Array.from({ length: 3 }).map((_, index) => (
            <li key={index} className="case-card case-card-skeleton" aria-hidden="true">
              <div className="skeleton-line skeleton-line-lg" />
              <div className="skeleton-line" />
              <div className="skeleton-line skeleton-line-sm" />
            </li>
          ))}
        </ul>
      ) : null}

      {!error && !loading && items.length === 0 ? (
        <div className="explore-empty">
          <span className="explore-empty-mark" aria-hidden="true">
            <svg viewBox="0 0 48 48" width="48" height="48" fill="none">
              <circle cx="14" cy="32" r="6" stroke="var(--mint)" strokeWidth="2" />
              <circle cx="34" cy="16" r="6" stroke="var(--aqua)" strokeWidth="2" />
              <path d="M19 29 C 24 25, 26 20, 29 19" stroke="var(--text-faint)" strokeWidth="1.5" strokeDasharray="3 3" />
            </svg>
          </span>
          <h2 className="heading-3">
            {query || verdict ? "No cases match that filter" : "No cases have been recorded yet"}
          </h2>
          <p className="prose">
            {query || verdict
              ? "Try a broader search, or clear the verdict filter."
              : "ForkReason records a case once someone traces a relationship. Start the first one."}
          </p>
          <Link href="/trace" className="btn btn-primary">
            {query || verdict ? "Clear filters" : "Start a trace"}
          </Link>
        </div>
      ) : null}

      {items.length > 0 ? (
        <>
          <p className="explore-count" role="status">
            {total} case{total === 1 ? "" : "s"}
            {query ? ` matching “${query}”` : ""}
          </p>
          <ul className="case-grid">
            {items.map((item) => (
              <li key={item.id}>
                <CaseCardView item={item} />
              </li>
            ))}
          </ul>

          {hasMore || offset > 0 ? (
            <nav className="explore-pagination" aria-label="Pagination">
              <button
                type="button"
                className="btn btn-secondary"
                disabled={offset === 0 || loading}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </button>
              <span className="explore-pagination-label mono">
                {offset + 1}–{offset + items.length} of {total}
              </span>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={!hasMore || loading}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </button>
            </nav>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function CaseCardView({ item }: { item: CaseCard }) {
  const meta = item.verdict ? VERDICT_META[item.verdict] : null;
  const confidence = item.confidence ? CONFIDENCE_META[item.confidence] : null;

  return (
    <Link href={`/case/${item.id}`} className="case-card">
      <div className="case-card-head">
        {meta ? <span className={`badge badge-${meta.tone}`}>{meta.label}</span> : <span className="badge badge-muted">unresolved</span>}
        {item.revision > 1 ? (
          <span className="badge badge-amber">revision {item.revision}</span>
        ) : null}
      </div>

      <p className="case-card-pair mono">
        <span>{item.origin_repo}</span>
        <span className="case-card-arrow" aria-label="compared with">
          →
        </span>
        <span>{item.target_repo}</span>
      </p>

      <div className="case-card-foot">
        {confidence ? (
          <span className={`badge badge-${confidence.tone}`}>{item.confidence}</span>
        ) : null}
        <span className="case-card-hash mono">{item.manifest_hash?.slice(0, 12)}</span>
      </div>
    </Link>
  );
}