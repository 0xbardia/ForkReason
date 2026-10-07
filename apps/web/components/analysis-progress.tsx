"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { api, ApiClientError, type AnalysisJob, type EvidenceCard } from "@/lib/api";
import { shortSha, STAGE_LABEL } from "@/lib/presentation";

const POLL_MS = 2000;

/**
 * Analysis progress.
 *
 * Shows the pipeline's real stage states and nothing else: no invented
 * percentage, no timer pretending to predict an ETA. A stage reads "working"
 * only while the worker says it is, and the elapsed clock is labelled as
 * elapsed rather than remaining.
 *
 * Evidence previews appear as soon as they exist, because watching a forensic
 * pipeline produce findings is more interesting than watching a spinner.
 */
export function AnalysisProgress({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [preview, setPreview] = useState<EvidenceCard[]>([]);
  // Read inside the interval rather than during render: `Date.now()` in the
  // render body is an impure read, and React may render a component more than
  // once, which would restart the clock and make the elapsed time jump.
  const startedAt = useRef<number | null>(null);
  const navigated = useRef(false);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    async function poll() {
      try {
        const next = await api.getAnalysis(jobId);
        if (cancelled) return;
        setJob(next);
        setError(null);

        // Once a case exists, peek at its evidence so the page shows findings
        // rather than an empty progress list.
        if (next.case_id && preview.length === 0) {
          try {
            const evidence = await api.getEvidence(next.case_id, { limit: 6 });
            if (!cancelled) setPreview(evidence.items);
          } catch {
            /* the case may still be committing; the next poll will retry */
          }
        }

        if (next.status === "succeeded" && next.case_id && !navigated.current) {
          navigated.current = true;
          router.replace(`/case/${next.case_id}`);
          return;
        }
        if (next.status === "succeeded" && !next.case_id) {
          // Succeeded but no case recorded: show a clear terminal state rather
          // than looping forever.
          setError("Analysis completed but no case was recorded.");
          return;
        }
        if (["failed", "cancelled", "timed_out"].includes(next.status)) {
          return;
        }
      } catch (err) {
        if (cancelled) return;
        // A transient failure should not replace the last known good state.
        setError(
          err instanceof ApiClientError && err.isNetwork
            ? "Lost contact with the analysis service. Reconnecting…"
            : err instanceof ApiClientError
              ? err.message
              : "Progress could not be read.",
        );
      }
      if (!cancelled) timer = window.setTimeout(() => void poll(), POLL_MS);
    }

    void poll();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [jobId, router, preview.length]);

  useEffect(() => {
    startedAt.current = Date.now();
    const id = window.setInterval(() => {
      const started = startedAt.current;
      if (started === null) return;
      setElapsed(Math.round((Date.now() - started) / 1000));
    }, 1000);
    return () => window.clearInterval(id);
  }, []);

  const terminal = job && ["failed", "cancelled", "timed_out"].includes(job.status);
  const statusLabel = terminal
    ? job.status === "timed_out"
      ? "Analysis exceeded its time budget"
      : job.status === "cancelled"
        ? "Analysis cancelled"
        : "Analysis failed"
    : error
      ? "Analysis unavailable"
      : "Analysis in progress";

  return (
    <div className="layout analysis-page">
      <header className="analysis-head">
        <p className="eyebrow">{statusLabel}</p>
        <h1 className="heading-2 analysis-pair">
          <span className="mono">{job?.origin.repo ?? "…"}</span>
          <span className="analysis-pair-arrow" aria-label="compared with">
            →
          </span>
          <span className="mono">{job?.target.repo ?? "…"}</span>
        </h1>
        {job ? (
          <p className="analysis-meta mono">
            <span title={job.origin.commit}>{shortSha(job.origin.commit, 10)}</span>
            <span aria-hidden="true"> · </span>
            <span title={job.target.commit}>{shortSha(job.target.commit, 10)}</span>
            <span aria-hidden="true"> · </span>
            <span>{elapsed}s elapsed</span>
          </p>
        ) : null}
      </header>

      <div className="analysis-grid">
        <section aria-labelledby="stages-heading" className="analysis-stages">
          <h2 id="stages-heading" className="eyebrow analysis-section-heading">
            Pipeline stages
          </h2>

          <ol className="stage-list">
            {(job?.stages ?? []).map((stage) => (
              <li key={stage.name} className="stage-item" data-state={stage.state}>
                <span className="stage-indicator" aria-hidden="true">
                  {stage.state === "complete" ? "✓" : stage.state === "working" ? "◐" : stage.state === "failed" ? "✕" : "·"}
                </span>
                <span className="stage-name">{STAGE_LABEL[stage.name] ?? stage.name}</span>
                <span className="stage-state">
                  {stage.state === "complete"
                    ? "complete"
                    : stage.state === "working"
                      ? "working"
                      : stage.state === "failed"
                        ? "failed"
                        : "waiting"}
                </span>
              </li>
            ))}
          </ol>

          {!job && !error ? (
            <ul className="stage-list" aria-hidden="true">
              {Array.from({ length: 8 }).map((_, index) => (
                <li key={index} className="stage-item" data-state="pending">
                  <span className="stage-indicator">·</span>
                  <span className="stage-name skeleton-line" style={{ width: "9rem" }} />
                </li>
              ))}
            </ul>
          ) : null}

          {error && !terminal ? (
            <p className="analysis-note" role="status">
              {error}
            </p>
          ) : null}

          {terminal ? (
            <div className="analysis-terminal" role="alert">
              <h3 className="heading-3">
                {job.status === "cancelled"
                  ? "This analysis was cancelled"
                  : job.status === "timed_out"
                    ? "This analysis ran out of time"
                    : "This analysis could not complete"}
              </h3>
              <p className="prose">
                {job.error_message ??
                  "The failure was logged. No case was recorded, so nothing was published."}
              </p>
              {job.error_code ? (
                <p className="analysis-error-code mono">{job.error_code}</p>
              ) : null}
              <div className="analysis-terminal-actions">
                <Link href="/trace" className="btn btn-secondary">
                  Start another trace
                </Link>
                <Link href="/explore" className="btn btn-ghost">
                  Browse cases
                </Link>
              </div>
            </div>
          ) : null}
        </section>

        <aside className="analysis-aside">
          <h2 className="eyebrow analysis-section-heading">Evidence so far</h2>
          {preview.length > 0 ? (
            <ul className="analysis-preview">
              {preview.map((item) => (
                <li key={item.id} className="analysis-preview-item">
                  <span className={`badge badge-${item.strength === "HIGH" ? "coral" : item.strength === "MEDIUM" ? "amber" : "muted"}`}>
                    {item.strength}
                  </span>
                  <p className="analysis-preview-type">{item.evidence_type.replace(/_/g, " ")}</p>
                  <p className="analysis-preview-why">{item.rationale}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="analysis-note">
              Evidence appears here as the pipeline finds it. Nothing is shown
              before it is actually discovered.
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}
