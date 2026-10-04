"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { RepoInput } from "@/components/repo-input";
import { LineageVisual } from "@/components/lineage-visual";
import { api, ApiClientError, type RepositorySummary } from "@/lib/api";

/**
 * The dedicated trace surface.
 *
 * Same validation contract as the hero panel, but with room for a persistent
 * lineage visual and a clearer explanation of what will happen — this is the
 * page a user lands on from the nav, so it should stand on its own.
 */
export function TraceWorkspace() {
  const router = useRouter();
  const [origin, setOrigin] = useState("");
  const [target, setTarget] = useState("");
  const [validated, setValidated] = useState<{
    origin: RepositorySummary;
    target: RepositorySummary;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [starting, setStarting] = useState(false);
  const timer = useRef<number | null>(null);
  const controller = useRef<AbortController | null>(null);
  const sequence = useRef(0);

  const ready = origin.trim().length >= 4 && target.trim().length >= 4;

  const validate = useCallback(async (o: string, t: string) => {
    const token = ++sequence.current;
    controller.current?.abort();
    const ac = new AbortController();
    controller.current = ac;
    setChecking(true);
    setError(null);
    try {
      const result = await api.validateRepositories(o, t, ac.signal);
      if (token !== sequence.current) return;
      setValidated({ origin: result.origin, target: result.target });
      setError(null);
    } catch (err) {
      if (token !== sequence.current || ac.signal.aborted) return;
      setValidated(null);
      setError(err instanceof ApiClientError ? err.message : "Repositories could not be validated.");
    } finally {
      if (token === sequence.current) setChecking(false);
    }
  }, []);

  useEffect(() => {
    if (!ready) {
      setValidated(null);
      return;
    }
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void validate(origin, target), 500);
    return () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    };
  }, [origin, target, ready, validate]);

  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
      controller.current?.abort();
    },
    [],
  );

  async function start() {
    if (!ready || starting) return;
    setStarting(true);
    setError(null);
    try {
      const response = await api.createAnalysis(origin, target);
      router.push(`/analysis/${response.job.job_id}`);
    } catch (err) {
      setStarting(false);
      setError(
        err instanceof ApiClientError ? err.message : "The analysis could not be started.",
      );
    }
  }

  return (
    <div className="layout trace-page">
      <header className="trace-page-head">
        <p className="eyebrow">New trace</p>
        <h1 className="heading-1">Compare two repositories</h1>
        <p className="lead">
          ForkReason pins an immutable commit for each repository, then runs a
          deterministic forensic pipeline across six evidence layers before any
          judgement is made. Repository code is read, never executed.
        </p>
      </header>

      <div className="trace-page-grid">
        <div className="trace-page-form">
          <div className="trace-page-inputs">
            <RepoInput
              label="the repository you suspect"
              role="origin"
              value={origin}
              onChange={setOrigin}
              repository={validated?.origin ?? null}
              error={error && !validated ? error : null}
              checking={checking}
              disabled={starting}
            />
            <RepoInput
              label="the repository to explain"
              role="target"
              value={target}
              onChange={setTarget}
              repository={validated?.target ?? null}
              error={null}
              checking={checking}
              disabled={starting}
            />
          </div>

          {error && validated ? (
            <p className="trace-error" role="alert">
              {error}
            </p>
          ) : null}

          <div className="trace-actions">
            <button
              type="button"
              className="btn btn-primary btn-lg"
              onClick={() => void start()}
              disabled={!ready || starting}
            >
              {starting ? "Starting analysis…" : "Trace lineage"}
            </button>
            <p className="trace-hint">
              {validated
                ? "Both repositories are public. Analysis usually takes under a minute."
                : "Public GitHub repositories only, in V1."}
            </p>
          </div>

          <details className="trace-advanced">
            <summary>What ForkReason does with your input</summary>
            <ul>
              <li>
                Fetches repository metadata and pins the current default-branch
                commit. Nothing is analyzed at a moving branch reference.
              </li>
              <li>
                Extracts the tracked files at that commit. No package install, no
                build, no test execution, no repository code run in any form.
              </li>
              <li>
                Reads commit history, then computes deterministic fingerprints,
                chronology, shared-upstream candidates and alternative
                explanations.
              </li>
              <li>
                Produces a bounded evidence manifest and a SHA-256 hash of it. A
                wallet signature is only needed to record the finding on chain.
              </li>
            </ul>
          </details>
        </div>

        <aside className="trace-page-aside">
          <div className="glass trace-page-visual" data-tint="aqua">
            <p className="eyebrow">What the analysis reconstructs</p>
            <LineageVisual compact />
          </div>
        </aside>
      </div>
    </div>
  );
}