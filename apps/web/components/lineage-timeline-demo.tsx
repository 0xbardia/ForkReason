"use client";

import { useId } from "react";

/**
 * Lineage timeline demonstration.
 *
 * This is the section that makes the product's core argument visible without a
 * wall of text: a repository's history is not a list of commits, it is a
 * sequence in which a specific defect appears, persists, and is fixed — and
 * whether the second repository's earliest commit still contains that defect is
 * what decides direction.
 *
 * Everything drawn here is a labelled, deterministic illustration of the rule
 * the engine actually enforces. It is not live data and is labelled as such.
 */

interface Marker {
  at: number;
  lane: "origin" | "target";
  kind: "commit" | "signal" | "defect" | "fix";
  title: string;
  detail: string;
  sha: string;
}

const MARKERS: Marker[] = [
  {
    at: 4,
    lane: "origin",
    kind: "commit",
    title: "origin exists",
    detail: "First commit. Establishes that derivation could happen from here.",
    sha: "3f9c1ab",
  },
  {
    at: 26,
    lane: "origin",
    kind: "defect",
    title: "off-by-one introduced",
    detail:
      "chunked_transfer() drops the final byte. A distinctive mistake, not a common one.",
    sha: "8d40e77",
  },
  {
    at: 41,
    lane: "origin",
    kind: "signal",
    title: "rare constant added",
    detail: "CHECKPOINT_MAGIC 0x5F3759DF, undocumented, never explained.",
    sha: "b17c9e0",
  },
  {
    at: 63,
    lane: "origin",
    kind: "fix",
    title: "bug fixed",
    detail: "Off-by-one corrected. The buggy behaviour now exists only in history.",
    sha: "c2a55f1",
  },
  {
    at: 74,
    lane: "target",
    kind: "commit",
    title: "target appears",
    detail: "Its first commit already contains the unfixed off-by-one.",
    sha: "5e70b31",
  },
];

const LANE_LABEL = {
  origin: "origin/repo",
  target: "target/repo",
} as const;

export function LineageTimeline() {
  const gradientId = useId();
  const axisId = useId();

  const height = 260;
  const laneY = { origin: 96, target: 168 };
  const padX = 26;
  const width = 620;
  const innerWidth = width - padX * 2;

  const x = (at: number) => padX + (at / 100) * innerWidth;

  return (
    <section className="section timeline-section" aria-labelledby="timeline-heading">
      <div className="layout">
        <header className="section-head">
          <p className="eyebrow">How a direction is proven</p>
          <h2 className="heading-2" id="timeline-heading">
            Chronology is the part similarity cannot fake
          </h2>
          <p className="section-note">
            Matching code proves two things share text. It says nothing about
            which came first. ForkReason reads both histories and looks for a
            defect that existed in one repository before the other appeared —
            because a bug nobody else writes identically is a timestamp you
            cannot forge.
          </p>
        </header>

        <figure className="timeline-figure">
          <figcaption className="timeline-caption">
            <span className="timeline-caption-tag" data-kind="fixture">
              Illustrative fixture
            </span>
            Demonstrates the rule the engine enforces on real repositories. Not
            live analysis data.
          </figcaption>

          <div className="timeline-canvas">
            <svg
              viewBox={`0 0 ${width} ${height}`}
              role="img"
              aria-labelledby={axisId}
              preserveAspectRatio="xMidYMid meet"
            >
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="var(--mint)" />
                  <stop offset="52%" stopColor="var(--aqua)" />
                  <stop offset="100%" stopColor="var(--signal)" />
                </linearGradient>
              </defs>

              {/* Lane tracks */}
              {(["origin", "target"] as const).map((lane) => (
                <g key={lane}>
                  <text
                    className="timeline-lane-label"
                    x={padX}
                    y={laneY[lane] - 20}
                  >
                    {LANE_LABEL[lane]}
                  </text>
                  <line
                    className="timeline-track"
                    x1={padX}
                    y1={laneY[lane]}
                    x2={width - padX}
                    y2={laneY[lane]}
                  />
                </g>
              ))}

              {/* The lineage edge: origin -> target */}
              <path
                className="timeline-edge"
                d={`M ${x(63)} ${laneY.origin}
                    C ${x(66)} ${laneY.origin},
                      ${x(70)} ${laneY.target},
                      ${x(74)} ${laneY.target}`}
                stroke={`url(#${gradientId})`}
              />

              {/* Markers */}
              {MARKERS.map((marker) => {
                const y = laneY[marker.lane];
                return (
                  <g key={marker.title} className="timeline-marker">
                    <line
                      className="timeline-stem"
                      data-kind={marker.kind}
                      x1={x(marker.at)}
                      y1={y}
                      x2={x(marker.at)}
                      y2={marker.lane === "origin" ? y + 22 : y - 22}
                    />
                    <circle
                      className="timeline-node"
                      data-kind={marker.kind}
                      cx={x(marker.at)}
                      cy={y}
                      r={marker.kind === "commit" ? 6 : 5}
                    />
                    <text
                      className="timeline-sha"
                      x={x(marker.at)}
                      y={marker.lane === "origin" ? y + 36 : y - 30}
                      textAnchor="middle"
                    >
                      {marker.sha}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>

          {/* The same information, structured and reachable by keyboard/screen
              reader rather than living only inside an SVG. */}
          <ol className="timeline-events">
            {MARKERS.map((marker) => (
              <li key={marker.title} className="timeline-event" data-kind={marker.kind}>
                <span className="timeline-event-lane mono">{marker.lane}</span>
                <span className="timeline-event-title">{marker.title}</span>
                <span className="timeline-event-detail">{marker.detail}</span>
                <span className="timeline-event-sha mono">{marker.sha}</span>
              </li>
            ))}
          </ol>

          <div className="timeline-verdict">
            <p className="timeline-verdict-label">What the engine concludes</p>
            <p className="timeline-verdict-body">
              The target&apos;s earliest commit already contains the origin&apos;s
              unfixed defect, so the defect was carried across — not independently
              reinvented. Direction is <strong>origin → target</strong>, and this
              survives even if every other signal were removed.
            </p>
          </div>
        </figure>
      </div>
    </section>
  );
}