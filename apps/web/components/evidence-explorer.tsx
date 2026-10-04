"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { api, ApiClientError, type EvidenceCard } from "@/lib/api";
import { LAYER_LABEL, shortSha } from "@/lib/presentation";

const LAYERS = ["CODE", "ARCHITECTURE", "HISTORY", "BUG", "TEST", "LANGUAGE"] as const;
const STRENGTHS = ["HIGH", "MEDIUM", "LOW"] as const;

/** Evidence explorer: the filterable full set behind the case report. */
export function EvidenceExplorer({ caseId }: { caseId: string }) {
  const [items, setItems] = useState<EvidenceCard[]>([]);
  const [facets, setFacets] = useState<{ layers: Record<string, number>; strengths: Record<string, number> }>({
    layers: {},
    strengths: {},
  });
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [layer, setLayer] = useState<string>("");
  const [strength, setStrength] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (nextOffset: number, nextLayer: string, nextStrength: string) => {
      setLoading(true);
      setError(null);
      try {
        const result = await api.getEvidence(
          caseId,
          {
            layer: nextLayer || undefined,
            strength: nextStrength || undefined,
            limit: 50,
            offset: nextOffset,
          },
        );
        setItems(result.items);
        setFacets(result.facets);
        setTotal(result.total);
        setHasMore(result.has_more);
      } catch (err) {
        setError(
          err instanceof ApiClientError ? err.message : "Evidence could not be loaded.",
        );
      } finally {
        setLoading(false);
      }
    },
    [caseId],
  );

  useEffect(() => {
    void load(offset, layer, strength);
  }, [load, offset, layer, strength]);

  return (
    <div className="layout evidence-page">
      <header className="evidence-page-head">
        <Link href={`/case/${caseId}`} className="evidence-back">
          ← Back to case report
        </Link>
        <h1 className="heading-2">Evidence explorer</h1>
        <p className="lead">
          Every finding, with the file and commit it came from. Filter by DNA layer
          or strength.
        </p>
      </header>

      <div className="evidence-filters" role="group" aria-label="Evidence filters">
        <div className="evidence-filter-group">
          <span className="eyebrow">Layer</span>
          <div className="evidence-chips">
            <button
              type="button"
              className="chip"
              data-active={layer === ""}
              aria-pressed={layer === ""}
              onClick={() => {
                setOffset(0);
                setLayer("");
              }}
            >
              All
            </button>
            {LAYERS.map((item) => (
              <button
                key={item}
                type="button"
                className="chip"
                data-layer={item}
                data-active={layer === item}
                aria-pressed={layer === item}
                disabled={!facets.layers[item]}
                onClick={() => {
                  setOffset(0);
                  setLayer(layer === item ? "" : item);
                }}
              >
                {LAYER_LABEL[item]}
                {facets.layers[item] ? <span className="chip-count">{facets.layers[item]}</span> : null}
              </button>
            ))}
          </div>
        </div>

        <div className="evidence-filter-group">
          <span className="eyebrow">Strength</span>
          <div className="evidence-chips">
            <button
              type="button"
              className="chip"
              data-active={strength === ""}
              aria-pressed={strength === ""}
              onClick={() => {
                setOffset(0);
                setStrength("");
              }}
            >
              All
            </button>
            {STRENGTHS.map((item) => (
              <button
                key={item}
                type="button"
                className="chip"
                data-strength={item}
                data-active={strength === item}
                aria-pressed={strength === item}
                disabled={!facets.strengths[item]}
                onClick={() => {
                  setOffset(0);
                  setStrength(strength === item ? "" : item);
                }}
              >
                {item}
                {facets.strengths[item] ? (
                  <span className="chip-count">{facets.strengths[item]}</span>
                ) : null}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error ? <p className="analysis-note" role="alert">{error}</p> : null}

      <p className="explore-count" role="status" aria-live="polite">
        {loading && items.length === 0 ? "Loading evidence…" : `${total} evidence item${total === 1 ? "" : "s"}`}
      </p>

      <ul className="evidence-list">
        {items.map((item) => (
          <li key={item.id}>
            <article className="evidence-row" data-conflicting={item.is_conflicting}>
              <div className="evidence-row-head">
                <span className={`badge badge-${item.strength === "HIGH" ? "coral" : item.strength === "MEDIUM" ? "amber" : "muted"}`}>
                  {item.strength}
                </span>
                <span className="evidence-layer">{LAYER_LABEL[item.dna_layer] ?? item.dna_layer}</span>
                <span className="evidence-type mono">{item.evidence_type.replace(/_/g, " ")}</span>
                {item.is_conflicting ? <span className="badge badge-coral">conflicts with verdict</span> : null}
              </div>
              <p className="evidence-why">{item.rationale}</p>
              <div className="evidence-sources">
                <div className="evidence-source">
                  <span className="eyebrow">Origin</span>
                  <span className="mono evidence-source-repo">{item.origin.repo}</span>
                  {item.origin.path ? <span className="mono evidence-source-path">{item.origin.path}</span> : null}
                  {item.origin.commit ? (
                    <span className="mono evidence-source-commit" title={item.origin.commit}>
                      {shortSha(item.origin.commit)}
                    </span>
                  ) : null}
                </div>
                <div className="evidence-source">
                  <span className="eyebrow">Target</span>
                  <span className="mono evidence-source-repo">{item.target.repo}</span>
                  {item.target.path ? <span className="mono evidence-source-path">{item.target.path}</span> : null}
                  {item.target.commit ? (
                    <span className="mono evidence-source-commit" title={item.target.commit}>
                      {shortSha(item.target.commit)}
                    </span>
                  ) : null}
                </div>
              </div>
              {item.excerpt ? <pre className="evidence-excerpt">{item.excerpt}</pre> : null}
            </article>
          </li>
        ))}
      </ul>

      {items.length === 0 && !loading ? (
        <p className="analysis-note">No evidence matches this filter combination.</p>
      ) : null}

      {hasMore || offset > 0 ? (
        <nav className="explore-pagination" aria-label="Evidence pagination">
          <button
            type="button"
            className="btn btn-secondary"
            disabled={offset === 0 || loading}
            onClick={() => setOffset(Math.max(0, offset - 50))}
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
            onClick={() => setOffset(offset + 50)}
          >
            Next
          </button>
        </nav>
      ) : null}
    </div>
  );
}