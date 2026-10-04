/** Shared presentational primitives. */

import type { Confidence, Direction, Verdict } from "@/lib/api";

/** Verdict → accent colour and label, bound once so a verdict looks the same
 *  everywhere it appears. */
export const VERDICT_META: Record<
  Verdict,
  { label: string; tone: "coral" | "amber" | "volt" | "aqua" | "signal" | "muted"; blurb: string }
> = {
  LIKELY_DERIVED: {
    label: "Likely derived",
    tone: "coral",
    blurb: "Evidence supports one repository developing from the other.",
  },
  HEAVILY_DERIVED: {
    label: "Heavily derived",
    tone: "amber",
    blurb: "A real lineage, but the implementation has since diverged.",
  },
  INDEPENDENT: {
    label: "Independent",
    tone: "volt",
    blurb: "Similarity is consistent with implementing the same specification.",
  },
  SHARED_UPSTREAM: {
    label: "Shared upstream",
    tone: "aqua",
    blurb: "Both repositories descend from a common ancestor.",
  },
  DECLARED_FORK: {
    label: "Declared fork",
    tone: "signal",
    blurb: "One repository declares the other as its upstream.",
  },
  INSUFFICIENT_EVIDENCE: {
    label: "Insufficient evidence",
    tone: "muted",
    blurb: "The available evidence does not support a conclusion either way.",
  },
};

export const CONFIDENCE_META: Record<Confidence, { tone: string; label: string }> = {
  HIGH: { tone: "mint", label: "High confidence" },
  MEDIUM: { tone: "amber", label: "Medium confidence" },
  LOW: { tone: "muted", label: "Low confidence" },
};

export const DIRECTION_LABEL: Record<Direction, string> = {
  ORIGIN_TO_TARGET: "origin → target",
  TARGET_TO_ORIGIN: "target → origin",
  NONE: "no direction",
};

export const LAYER_LABEL: Record<string, string> = {
  CODE: "Code",
  ARCHITECTURE: "Architecture",
  HISTORY: "History",
  BUG: "Bug",
  TEST: "Test",
  LANGUAGE: "Language",
};

export const STAGE_LABEL: Record<string, string> = {
  repository_snapshots: "Repository snapshots",
  commit_history: "Commit history",
  structural_fingerprints: "Structural fingerprints",
  historical_signals: "Historical signals",
  shared_upstream: "Shared upstream",
  alternative_explanations: "Alternative explanations",
  evidence_manifest: "Evidence manifest",
  consensus_preparation: "Consensus preparation",
};

export const EXPLANATION_LABEL: Record<string, string> = {
  TARGET_DERIVED_FROM_ORIGIN: "Target derived from origin",
  SHARED_UPSTREAM: "Shared upstream",
  INDEPENDENT_SAME_SPEC: "Independent, same specification",
  INSUFFICIENT_HISTORY: "Insufficient history",
  DECLARED_FORK: "Declared fork",
  POST_DERIVATION_DIVERGENCE: "Derived, then heavily changed",
};

export function shortSha(sha: string | null | undefined, length = 7): string {
  if (!sha) return "—";
  return sha.slice(0, length);
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function formatDate(iso: string | number | null | undefined): string {
  if (iso === null || iso === undefined || iso === "") return "—";
  const date = typeof iso === "number" ? new Date(iso * 1000) : new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function relativeTime(iso: string | null | undefined): string {
  // Every other formatter in this module answers an absent value with an em
  // dash. Returning an empty string here left callers rendering an empty
  // element, which reads as a layout bug rather than as missing data.
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(iso);
}

/** Truncate without cutting mid-word where avoidable. */
export function clamp(text: string, max: number): string {
  if (text.length <= max) return text;
  // Cut on a code-point boundary, not a UTF-16 index. Slicing between the two
  // halves of an emoji leaves a lone surrogate, which renders as a replacement
  // character in the excerpt.
  const characters = [...text];
  if (characters.length > max) characters.length = max;
  const slice = characters.join("");
  const lastSpace = slice.lastIndexOf(" ");
  const body = (lastSpace > max * 0.6 ? slice.slice(0, lastSpace) : slice).trimEnd();
  return `${body}…`;
}

/** Strip characters that have no business in a rendered excerpt. */
export function sanitizeExcerpt(text: string | null | undefined, max = 240): string {
  if (!text) return "";
  // Control characters are removed deliberately: repository text is untrusted
  // and reaches this function from analyzed source, so it can contain NUL, ESC
  // and friends that would corrupt a rendered excerpt. Tab, newline and
  // carriage return are preserved because they are legitimate whitespace.
  // eslint-disable-next-line no-control-regex -- see above
  return clamp(text.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g, " ").trim(), max);
}