"use client";

import { useId, useState } from "react";

/**
 * Repo DNA.
 *
 * Six concentric tracks, one per evidence layer, each with a distinct dash
 * signature so the layers are separable by shape and not only by colour. This
 * is deliberately not six cards: a radar of layered rings reads as a
 * measurement, which is what the layer actually is.
 */

const LAYERS = [
  {
    key: "HISTORY",
    label: "History",
    color: "var(--mint)",
    value: 0.86,
    dash: "1 0",
    blurb: "Commit chronology, first occurrence, and implementation order.",
    detail:
      "When did each distinctive signal first appear? A marker that exists in the origin before the target is directional evidence; the reverse is not.",
  },
  {
    key: "BUG",
    label: "Bug",
    color: "var(--coral)",
    value: 0.78,
    dash: "7 4",
    blurb: "Historically traceable defects and their fixes.",
    detail:
      "Do both projects carry the same unusual defect? Did the target appear after the origin fixed it, yet keep the pre-fix behaviour?",
  },
  {
    key: "CODE",
    label: "Code",
    color: "var(--aqua)",
    value: 0.72,
    dash: "2 3",
    blurb: "Normalized structure, uncommon fragments and constants.",
    detail:
      "Common framework vocabulary is discounted to nothing. What remains are the constants and ordered token sequences a refactor rarely erases.",
  },
  {
    key: "TEST",
    label: "Test",
    color: "var(--volt)",
    value: 0.58,
    dash: "9 3 2 3",
    blurb: "Uncommon tests, fixtures and regression scenarios.",
    detail:
      "Nobody independently writes a test called the same unusual thing twice. Shared distinctive test names are strong evidence.",
  },
  {
    key: "ARCHITECTURE",
    label: "Architecture",
    color: "var(--signal)",
    value: 0.51,
    dash: "4 4",
    blurb: "Topology, module boundaries and subsystem organization.",
    detail:
      "Shared subsystem names suggest the same decomposition. Generic directories such as src or utils are excluded, because everyone has them.",
  },
  {
    key: "LANGUAGE",
    label: "Language",
    color: "var(--amber)",
    value: 0.44,
    dash: "12 5",
    blurb: "Naming, comments, terminology and documentation phrasing.",
    detail:
      "Shared distinctive phrases in comments and docs are hard to produce independently, and easy to keep when copying.",
  },
] as const;

type LayerKey = (typeof LAYERS)[number]["key"];

export function RepoDna({
  /** Optional live values, e.g. real per-layer scores from a case. */
  values,
  title = "Repo DNA",
}: {
  values?: Partial<Record<LayerKey, number>>;
  title?: string;
}) {
  const uid = useId().replace(/:/g, "");
  const [active, setActive] = useState<LayerKey | null>(null);

  const size = 260;
  const centre = size / 2;
  const maxRadius = centre - 14;
  const ringGap = maxRadius / LAYERS.length;

  return (
    <div className="repo-dna">
      <div className="repo-dna-figure">
        <svg
          viewBox={`0 0 ${size} ${size}`}
          width="100%"
          className="repo-dna-svg"
          role="img"
          aria-label={`${title}: six evidence layers, each scored independently`}
        >
          <defs>
            {LAYERS.map((layer) => (
              <linearGradient
                key={layer.key}
                id={`dna-${uid}-${layer.key}`}
                x1="0"
                y1="0"
                x2="1"
                y2="1"
              >
                <stop offset="0%" stopColor={layer.color} stopOpacity="0.95" />
                <stop offset="100%" stopColor={layer.color} stopOpacity="0.4" />
              </linearGradient>
            ))}
          </defs>

          {/* track rings */}
          {LAYERS.map((layer, index) => {
            const radius = maxRadius - index * ringGap;
            const value = values?.[layer.key] ?? layer.value;
            return (
              <circle
                key={layer.key}
                cx={centre}
                cy={centre}
                r={radius}
                fill="none"
                stroke="var(--viz-grid-line)"
                strokeWidth={ringGap * 0.62}
              />
            );
          })}

          {/* scored arcs, drawn over their track */}
          {LAYERS.map((layer, index) => {
            const radius = maxRadius - index * ringGap;
            const value = Math.max(0, Math.min(1, values?.[layer.key] ?? layer.value));
            const circumference = 2 * Math.PI * radius;
            const dash = circumference * value;
            const isActive = active === layer.key;
            const dimmed = active !== null && !isActive;
            // Each layer starts at a different angle so the rings form a
            // spiral rather than six concentric arcs.
            const rotation = -90 + index * 24;
            return (
              <circle
                key={layer.key}
                cx={centre}
                cy={centre}
                r={radius}
                fill="none"
                stroke={`url(#dna-${uid}-${layer.key})`}
                strokeWidth={ringGap * 0.62}
                strokeLinecap="round"
                strokeDasharray={`${dash} ${circumference - dash}`}
                transform={`rotate(${rotation} ${centre} ${centre})`}
                opacity={dimmed ? 0.24 : 1}
                style={{ transition: "opacity 240ms var(--ease-out)" }}
              />
            );
          })}

          {/* centre mark */}
          <circle cx={centre} cy={centre} r={5} fill="var(--mint)" />
          <circle cx={centre} cy={centre} r={11} fill="none" stroke="var(--mint)" strokeWidth="1" opacity="0.4" />
        </svg>

        <span className="repo-dna-corner-label eyebrow" aria-hidden="true">
          six layers
        </span>
      </div>

      <div className="repo-dna-detail">
        <ul className="repo-dna-list" role="list">
          {LAYERS.map((layer) => {
            const value = values?.[layer.key] ?? layer.value;
            return (
              <li key={layer.key}>
                <button
                  type="button"
                  className="repo-dna-row"
                  data-active={active === layer.key}
                  aria-expanded={active === layer.key}
                  onMouseEnter={() => setActive(layer.key)}
                  onMouseLeave={() => setActive(null)}
                  onFocus={() => setActive(layer.key)}
                  onBlur={() => setActive(null)}
                  onClick={() => setActive(active === layer.key ? null : layer.key)}
                >
                  <span className="repo-dna-swatch" style={{ background: layer.color }} aria-hidden="true" />
                  <span className="repo-dna-name">{layer.label}</span>
                  <span className="repo-dna-bar" aria-hidden="true">
                    <span
                      className="repo-dna-bar-fill"
                      style={{
                        width: `${Math.round(value * 100)}%`,
                        background: layer.color,
                      }}
                    />
                  </span>
                  <span className="repo-dna-value mono">
                    {layer.key === "HISTORY" || layer.key === "BUG" ? "strong" : value >= 0.5 ? "medium" : "weak"}
                  </span>
                  <span className="sr-only">
                    {layer.label}: {layer.blurb}
                  </span>
                </button>
                {active === layer.key ? (
                  <p className="repo-dna-explain">{layer.detail}</p>
                ) : null}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}