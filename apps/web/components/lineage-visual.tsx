"use client";

import { useEffect, useId, useRef, useState } from "react";

/**
 * Interactive lineage visual.
 *
 * The hero needs to show what the product does without a screenshot, so this
 * draws the actual argument: two repositories, the signals that appear on a
 * timeline, and a shared ancestor that explains the overlap better than
 * copying would.
 *
 * It reacts to pointer position with a small parallax on the field nodes, and
 * every state is also expressed as text for assistive technology — the SVG is
 * `aria-hidden`, and the description below it carries the same information.
 */

interface Signal {
  id: string;
  label: string;
  layer: string;
  strength: "strong" | "medium" | "weak";
}

const SIGNALS: Signal[] = [
  { id: "s1", label: "shared constants", layer: "CODE", strength: "strong" },
  { id: "s2", label: "commit chronology", layer: "HISTORY", strength: "strong" },
  { id: "s3", label: "pre-fix defect", layer: "BUG", strength: "strong" },
  { id: "s4", label: "test names", layer: "TEST", strength: "medium" },
  { id: "s5", label: "doc phrasing", layer: "LANGUAGE", strength: "medium" },
  { id: "s6", label: "module layout", layer: "ARCHITECTURE", strength: "medium" },
];

const LAYER_COLOR: Record<string, string> = {
  CODE: "var(--aqua)",
  ARCHITECTURE: "var(--signal)",
  HISTORY: "var(--mint)",
  BUG: "var(--coral)",
  TEST: "var(--volt)",
  LANGUAGE: "var(--amber)",
};

export function LineageVisual({ compact = false }: { compact?: boolean }) {
  const uid = useId().replace(/:/g, "");
  const wrapRef = useRef<HTMLDivElement>(null);
  const [pointer, setPointer] = useState({ x: 0, y: 0 });
  const [activeSignal, setActiveSignal] = useState<string | null>(null);

  // Pointer tracking is throttled to animation frames: without that, every
  // mousemove would trigger a React render.
  const frame = useRef<number | null>(null);
  useEffect(() => {
    const node = wrapRef.current;
    if (!node) return;
    const onMove = (event: PointerEvent) => {
      const rect = node.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - 0.5;
      const y = (event.clientY - rect.top) / rect.height - 0.5;
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      frame.current = requestAnimationFrame(() => {
        setPointer({ x: Math.max(-0.6, Math.min(0.6, x)), y: Math.max(-0.6, Math.min(0.6, y)) });
      });
    };
    const onLeave = () => setPointer({ x: 0, y: 0 });
    node.addEventListener("pointermove", onMove);
    node.addEventListener("pointerleave", onLeave);
    return () => {
      node.removeEventListener("pointermove", onMove);
      node.removeEventListener("pointerleave", onLeave);
      if (frame.current !== null) cancelAnimationFrame(frame.current);
    };
  }, []);

  const height = compact ? 168 : 244;
  const parallax = (depth: number) => ({
    transform: `translate3d(${pointer.x * depth * 14}px, ${pointer.y * depth * 10}px, 0)`,
  });

  return (
    <div className="lineage-visual" ref={wrapRef} data-compact={compact}>
      <svg
        viewBox={`0 0 460 ${height}`}
        width="100%"
        height={height}
        aria-hidden="true"
        className="lineage-svg"
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <linearGradient id={`edge-${uid}`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--mint)" />
            <stop offset="60%" stopColor="var(--aqua)" />
            <stop offset="100%" stopColor="var(--signal)" />
          </linearGradient>
          <filter id={`glow-${uid}`} x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <radialGradient id={`halo-${uid}`}>
            <stop offset="0%" stopColor="var(--aqua)" stopOpacity="0.32" />
            <stop offset="100%" stopColor="var(--aqua)" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* upstream halo */}
        <circle cx="330" cy="58" r="72" fill={`url(#halo-${uid})`} opacity="0.7" />

        {/* upstream candidate */}
        <g style={parallax(0.5)}>
          <line x1="330" y1="58" x2="122" y2="168" stroke="var(--amber)" strokeWidth="1.3" strokeDasharray="4 5" opacity="0.42" />
          <line x1="330" y1="58" x2="356" y2="176" stroke="var(--amber)" strokeWidth="1.3" strokeDasharray="4 5" opacity="0.42" />
          <circle cx="330" cy="58" r="7.5" fill="var(--ink)" stroke="var(--amber)" strokeWidth="2" />
          <circle cx="330" cy="58" r="2.4" fill="var(--amber)" />
          <text x="330" y="38" textAnchor="middle" className="lv-label" fill="var(--amber)">
            shared upstream
          </text>
        </g>

        {/* derivation edge: origin -> target */}
        <g style={parallax(0.9)}>
          <path
            d="M122 168 C 170 150, 250 96, 356 176"
            stroke={`url(#edge-${uid})`}
            strokeWidth="2.6"
            fill="none"
            strokeLinecap="round"
            filter={`url(#glow-${uid})`}
          />
          {/* directional tick, the visual cue for "origin came first" */}
          <path d="M228 116 l 13 -6 l -3 13 z" fill="var(--aqua)" opacity="0.9" />
        </g>

        {/* origin node */}
        <g style={parallax(1.3)}>
          <circle cx="122" cy="168" r="19" fill="var(--ink)" stroke="var(--mint)" strokeWidth="2.2" />
          <circle cx="122" cy="168" r="7" fill="var(--mint)" opacity="0.92" />
          <text x="122" y="206" textAnchor="middle" className="lv-node" fill="var(--mint)">
            origin
          </text>
          <text x="122" y="222" textAnchor="middle" className="lv-sub">
            earlier
          </text>
        </g>

        {/* target node */}
        <g style={parallax(1.6)}>
          <circle cx="356" cy="176" r="19" fill="var(--ink)" stroke="var(--signal)" strokeWidth="2.2" />
          <circle cx="356" cy="176" r="7" fill="var(--signal)" opacity="0.92" />
          <text x="356" y="214" textAnchor="middle" className="lv-node" fill="var(--signal)">
            target
          </text>
          <text x="356" y="230" textAnchor="middle" className="lv-sub">
            later
          </text>
        </g>

        {/* evidence markers riding the derivation edge */}
        {SIGNALS.map((signal, index) => {
          const t = 0.18 + index * 0.13;
          // Cubic Bezier point on the same path as the edge.
          const p0 = { x: 122, y: 168 };
          const p1 = { x: 170, y: 150 };
          const p2 = { x: 250, y: 96 };
          const p3 = { x: 356, y: 176 };
          const mt = 1 - t;
          const x = mt ** 3 * p0.x + 3 * mt ** 2 * t * p1.x + 3 * mt * t ** 2 * p2.x + t ** 3 * p3.x;
          const y = mt ** 3 * p0.y + 3 * mt ** 2 * t * p1.y + 3 * mt * t ** 2 * p2.y + t ** 3 * p3.y;
          const color = LAYER_COLOR[signal.layer] ?? "var(--aqua)";
          const r = signal.strength === "strong" ? 4.4 : signal.strength === "medium" ? 3.4 : 2.6;
          return (
            <g
              key={signal.id}
              style={parallax(0.8 + index * 0.1)}
              className="lv-signal"
              data-active={activeSignal === signal.id}
            >
              <circle cx={x} cy={y} r={r + 5} fill={color} opacity="0.16" />
              <circle cx={x} cy={y} r={r} fill={color} />
            </g>
          );
        })}
      </svg>

      {/* Accessible equivalent of the diagram above. */}
      <div className="sr-only">
        <p>
          Lineage diagram: the origin repository appears first, the target
          repository later. A dotted line links both to a shared upstream
          candidate. Six evidence markers sit along the derivation path.
        </p>
        <ul>
          {SIGNALS.map((signal) => (
            <li key={signal.id}>
              {signal.label} — {signal.layer} layer, {signal.strength} signal
            </li>
          ))}
        </ul>
      </div>

      {/* Interactive legend: hovering or focusing a row highlights its marker. */}
      <ul className="lineage-legend" role="list">
        {SIGNALS.map((signal, index) => (
          <li key={signal.id}>
            <button
              type="button"
              className="lineage-legend-item"
              data-layer={signal.layer}
              data-active={activeSignal === signal.id}
              onMouseEnter={() => setActiveSignal(signal.id)}
              onMouseLeave={() => setActiveSignal(null)}
              onFocus={() => setActiveSignal(signal.id)}
              onBlur={() => setActiveSignal(null)}
            >
              <span className="lineage-dot" aria-hidden="true" />
              <span className="lineage-legend-label">{signal.label}</span>
              <span className="lineage-legend-layer">{signal.layer}</span>
              <span className="sr-only">
                Signal {index + 1} of {SIGNALS.length}, {signal.strength} strength
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}