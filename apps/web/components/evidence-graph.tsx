"use client";

import { useMemo, useState } from "react";

import type { EvidenceCard, GraphEdge } from "@/lib/api";
import { LAYER_LABEL, VERDICT_META } from "@/lib/presentation";
import type { Verdict } from "@/lib/api";

/**
 * Evidence graph.
 *
 * Requirements this satisfies (spec FR-J-009):
 *  * interactive: hover or focus a node to highlight its paths;
 *  * keyboard operable: every node is a real button in the tab order;
 *  * not canvas-only: the node list below is the same data, always present;
 *  * readable on small screens: below `lg` the list is the default view and
 *    the diagram is hidden, because a miniature graph helps nobody.
 */

export interface GraphNode {
  id: string;
  kind: "repository" | "evidence" | "upstream" | "commit";
  label: string;
  detail?: string;
}

const LAYER_COLOR: Record<string, string> = {
  CODE: "var(--aqua)",
  ARCHITECTURE: "var(--signal)",
  HISTORY: "var(--mint)",
  BUG: "var(--coral)",
  TEST: "var(--volt)",
  LANGUAGE: "var(--amber)",
};

export function EvidenceGraph({
  nodes,
  edges,
  evidence,
  originRepo,
  targetRepo,
  sharedUpstream,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  evidence: EvidenceCard[];
  originRepo: string;
  targetRepo: string;
  sharedUpstream: string | null;
}) {
  const [focused, setFocused] = useState<string | null>(null);

  const adjacency = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const edge of edges) {
      if (!map.has(edge.subject_ref)) map.set(edge.subject_ref, new Set());
      if (!map.has(edge.object_ref)) map.set(edge.object_ref, new Set());
      map.get(edge.subject_ref)!.add(edge.object_ref);
      map.get(edge.object_ref)!.add(edge.subject_ref);
    }
    return map;
  }, [edges]);

  const connected = useMemo(() => {
    if (!focused) return null;
    const direct = adjacency.get(focused) ?? new Set<string>();
    return new Set<string>([focused, ...direct]);
  }, [focused, adjacency]);

  const highlightedEdges = useMemo(
    () => edges.filter((edge) => connected?.has(edge.subject_ref) && connected?.has(edge.object_ref)),
    [edges, connected],
  );

  /** Deterministic layout: three columns, so the same case always draws the same. */
  const layout = useMemo(() => {
    const repos = nodes.filter((n) => n.kind === "repository");
    const upstreams = nodes.filter((n) => n.kind === "upstream");
    const evidenceNodes = nodes.filter((n) => n.kind === "evidence");
    const placed: Array<{ node: GraphNode; x: number; y: number }> = [];

    repos.forEach((node, index) => {
      placed.push({ node, x: 70, y: 90 + index * 120 });
    });
    upstreams.forEach((node, index) => {
      placed.push({ node, x: 260, y: 60 + index * 90 });
    });
    evidenceNodes.forEach((node, index) => {
      const column = index % 2;
      const row = Math.floor(index / 2);
      placed.push({ node, x: 420 + column * 96, y: 56 + row * 58 });
    });
    return placed;
  }, [nodes]);

  const positions = new Map(layout.map((item) => [item.node.id, item]));
  const width = 560;
  const height = Math.max(260, 90 + Math.ceil(nodes.length / 2) * 58);

  return (
    <div className="evidence-graph">
      <div className="evidence-graph-canvas" data-hidden-mobile="true">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          width="100%"
          height={height}
          role="img"
          aria-label="Evidence graph connecting the two repositories, their evidence, and any shared upstream candidate"
        >
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--viz-edge-weak)" />
            </marker>
          </defs>

          {/* edges */}
          {highlightedEdges.map((edge) => {
            const from = positions.get(edge.subject_ref);
            const to = positions.get(edge.object_ref);
            if (!from || !to) return null;
            const contradiction = edge.relation.includes("contradict");
            return (
              <line
                key={edge.id}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke={contradiction ? "var(--viz-edge-contradiction)" : "var(--viz-edge-weak)"}
                strokeWidth={contradiction ? 1.6 : 1.1}
                strokeDasharray={edge.relation === "candidate_upstream" ? "4 4" : undefined}
                markerEnd="url(#arrow)"
                opacity={0.75}
              />
            );
          })}

          {/* nodes */}
          {layout.map(({ node, x, y }) => {
            const isFocused = focused === node.id;
            const dimmed = connected !== null && !connected.has(node.id);
            const evidenceItem = evidence.find((item) => item.id === node.id);
            const fill =
              node.kind === "repository"
                ? "var(--mint)"
                : node.kind === "upstream"
                  ? "var(--amber)"
                  : (LAYER_COLOR[evidenceItem?.dna_layer ?? ""] ?? "var(--aqua)");
            const radius = node.kind === "evidence" ? 7 : 11;
            return (
              <g
                key={node.id}
                opacity={dimmed ? 0.28 : 1}
                style={{ transition: "opacity 200ms var(--ease-out)" }}
              >
                <circle cx={x} cy={y} r={radius + 6} fill={fill} opacity={isFocused ? 0.22 : 0.09} />
                <circle cx={x} cy={y} r={radius} fill="var(--ink)" stroke={fill} strokeWidth="2" />
                {isFocused ? <circle cx={x} cy={y} r={radius + 4} fill="none" stroke={fill} strokeWidth="1" opacity="0.5" /> : null}
              </g>
            );
          })}
        </svg>
      </div>

      {/* Node list: the accessible, keyboard-operable equivalent of the graph.
          This is the primary control surface; the SVG is a visual echo. */}
      <div className="evidence-graph-nodes">
        <p className="eyebrow">Evidence graph</p>
        <ul role="list" className="graph-node-list">
          {nodes.map((node) => {
            const related = adjacency.get(node.id) ?? new Set<string>();
            const evidenceItem = evidence.find((item) => item.id === node.id);
            const isFocused = focused === node.id;
            const summary = evidenceItem
              ? `${evidenceItem.dna_layer} · ${evidenceItem.strength} · ${evidenceItem.rationale}`
              : (node.detail ?? "");
            return (
              <li key={node.id}>
                <button
                  type="button"
                  className="graph-node"
                  data-kind={node.kind}
                  data-focused={isFocused}
                  data-dimmed={connected !== null && !isFocused}
                  aria-pressed={isFocused}
                  onMouseEnter={() => setFocused(node.id)}
                  onMouseLeave={() => setFocused(null)}
                  onFocus={() => setFocused(node.id)}
                  onBlur={() => setFocused(null)}
                  onClick={() => setFocused(isFocused ? null : node.id)}
                >
                  <span className="graph-node-label mono">{node.label}</span>
                  <span className="graph-node-meta">
                    {node.kind === "evidence" ? LAYER_LABEL[evidenceItem?.dna_layer ?? ""] ?? node.kind : node.kind}
                    {related.size > 0 ? ` · ${related.size} connection${related.size === 1 ? "" : "s"}` : ""}
                  </span>
                  {isFocused && summary ? (
                    <span className="graph-node-summary">{summary}</span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

/** Build the node/edge lists the graph consumes from a case report. */
export function buildGraph(
  originRepo: string,
  targetRepo: string,
  evidence: EvidenceCard[],
  graph: GraphEdge[],
  sharedUpstream: string | null,
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes: GraphNode[] = [
    { id: originRepo, kind: "repository", label: originRepo, detail: "origin repository" },
    { id: targetRepo, kind: "repository", label: targetRepo, detail: "target repository" },
  ];
  if (sharedUpstream) {
    nodes.push({
      id: sharedUpstream,
      kind: "upstream",
      label: sharedUpstream,
      detail: "shared upstream candidate",
    });
  }
  for (const item of evidence) {
    nodes.push({
      id: item.id,
      kind: "evidence",
      label: LAYER_LABEL[item.dna_layer] ?? item.dna_layer,
      detail: item.evidence_type,
    });
  }

  const known = new Set(nodes.map((node) => node.id));
  const edges = graph.filter(
    (edge) => known.has(edge.subject_ref) && known.has(edge.object_ref),
  );
  return { nodes, edges };
}

/** Verdict colour used by the graph's repository nodes. */
export function verdictTone(verdict: Verdict | null): string {
  if (!verdict) return "var(--text-muted)";
  return VERDICT_META[verdict].tone;
}