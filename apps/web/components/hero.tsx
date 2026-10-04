"use client";

import { useEffect, useState } from "react";

import { TracePanel } from "@/components/trace-panel";

/**
 * Hero.
 *
 * The one job here is comprehension in ten seconds: what this is, what to do,
 * and why it is credible. So the headline is literal, the inputs are in the
 * first viewport, and the interactive lineage visual sits beside them rather
 * than below the fold.
 *
 * Validation runs on blur/debounce, not on every keystroke, and never blocks
 * the primary action.
 */
export function Hero() {
  const [origin, setOrigin] = useState("");
  const [target, setTarget] = useState("");
  return (
    <section className="hero" aria-labelledby="hero-heading">
      <div className="hero-grid">
        <div className="hero-copy">
          <p className="eyebrow hero-eyebrow">
            <span className="hero-eyebrow-dot" aria-hidden="true" />
            Software provenance on GenLayer
          </p>

          <h1 id="hero-heading" className="display hero-heading">
            Trace where software{" "}
            <span className="living hero-heading-accent">really came from.</span>
          </h1>

          <p className="lead hero-lead">
            ForkReason compares two repositories, reconstructs their development
            lineage from code, history, bugs and tests, weighs the innocent
            explanations alongside the obvious one, and records the finding as an
            immutable decision through GenLayer consensus.
          </p>

          <TracePanel origin={origin} target={target} onOrigin={setOrigin} onTarget={setTarget} />

          <p className="hero-reassurance">
            No wallet needed to analyze. You only sign when you want a finding
            recorded on chain or a challenge submitted.
          </p>
        </div>

        <div className="hero-visual" aria-hidden={false}>
          <div className="glass hero-visual-panel" data-tint="aqua">
            <div className="hero-visual-head">
              <span className="eyebrow">Live lineage reconstruction</span>
              <span className="hero-visual-tag mono">origin → target</span>
            </div>
            <HeroVisual />
          </div>

          <ul className="hero-facts">
            <li>
              <span className="hero-fact-value">6</span>
              <span className="hero-fact-label">evidence layers</span>
            </li>
            <li>
              <span className="hero-fact-value">0</span>
              <span className="hero-fact-label">repository code executed</span>
            </li>
            <li>
              <span className="hero-fact-value">∞</span>
              <span className="hero-fact-label">challengeable revisions</span>
            </li>
          </ul>
        </div>
      </div>
    </section>
  );
}

function HeroVisual() {
  const [t, setT] = useState(0);
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (reduce.matches) return;
    const id = window.setInterval(() => setT((v) => v + 1), 2600);
    return () => window.clearInterval(id);
  }, []);

  const stages = [
    { label: "origin", sub: "2021-04-02", x: 62, y: 168, tone: "mint" as const },
    { label: "signal", sub: "marker appears", x: 148, y: 126, tone: "aqua" as const },
    { label: "bug", sub: "defect present", x: 226, y: 108, tone: "coral" as const },
    { label: "fix", sub: "2021-07-01", x: 300, y: 126, tone: "amber" as const },
    { label: "target", sub: "2021-11-19", x: 392, y: 172, tone: "signal" as const },
  ];
  const path = "M62 168 C 108 150, 128 128, 148 126 C 190 122, 208 108, 226 108 C 264 108, 280 122, 300 126 C 346 134, 368 152, 392 172";

  return (
    <div className="hero-visual-body">
      <svg
        viewBox="0 0 460 210"
        width="100%"
        height={210}
        className="hero-timeline"
        role="img"
        aria-label="Timeline: the origin repository appears, a distinctive signal and a defect appear, the origin fixes the defect, then the target repository appears carrying the pre-fix behaviour"
      >
        <defs>
          <linearGradient id="hero-edge" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--mint)" />
            <stop offset="50%" stopColor="var(--aqua)" />
            <stop offset="100%" stopColor="var(--signal)" />
          </linearGradient>
        </defs>

        <path d={path} fill="none" stroke="var(--viz-grid-line)" strokeWidth="6" strokeLinecap="round" />
        <path
          d={path}
          fill="none"
          stroke="url(#hero-edge)"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeDasharray="320"
          strokeDashoffset={320 - ((t % 4) / 4) * 320}
          style={{ transition: "stroke-dashoffset 2.4s linear" }}
        />

        {stages.map((stage, index) => (
          <g key={stage.label}>
            <circle
              cx={stage.x}
              cy={stage.y}
              r={stage.label === "signal" || stage.label === "bug" ? 6 : 9}
              fill="var(--ink)"
              stroke={`var(--${stage.tone})`}
              strokeWidth="2"
            />
            <circle cx={stage.x} cy={stage.y} r="2.4" fill={`var(--${stage.tone})`} />
            <text
              x={stage.x}
              y={stage.y - 16}
              textAnchor="middle"
              className="hero-timeline-label"
              fill={`var(--${stage.tone})`}
            >
              {stage.label}
            </text>
            <text x={stage.x} y={stage.y + 26} textAnchor="middle" className="hero-timeline-sub">
              {stage.sub}
            </text>
            {index < stages.length - 1 ? null : null}
          </g>
        ))}
      </svg>
    </div>
  );
}