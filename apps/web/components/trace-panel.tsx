"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { RepoInput } from "@/components/repo-input";
import {
  api,
  ApiClientError,
  type RepositorySummary,
  type ValidateResponse,
} from "@/lib/api";

const DEBOUNCE_MS = 500;

/**
 * The primary action: validate both repositories, then start a durable analysis.
 *
 * Validation is debounced and non-blocking; the button stays enabled as soon as
 * both fields look plausible, because a visitor should never be stuck waiting
 * for a network round trip to start work.
 */
export function TracePanel({
  origin,
  target,
  onOrigin,
  onTarget,
}: {
  origin: string;
  target: string;
  onOrigin: (value: string) => void;
  onTarget: (value: string) => void;
}) {
  const router = useRouter();
  const [validated, setValidated] = useState<ValidateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [starting, setStarting] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const timer = useRef<number | null>(null);
  const controller = useRef<AbortController | null>(null);
  // Guards against a slow earlier validation overwriting a newer one.
  const sequence = useRef(0);

  const ready = origin.trim().length >= 4 && target.trim().length >= 4;

  const validate = useCallback(async (originValue: string, targetValue: string) => {
    const token = ++sequence.current;
    controller.current?.abort();
    const ac = new AbortController();
    controller.current = ac;
    setChecking(true);
    setError(null);
    try {
      const result = await api.validateRepositories(originValue, targetValue, ac.signal);
      if (token !== sequence.current) return;
      setValidated(result);
      setWarnings(result.warnings ?? []);
    } catch (err) {
      if (token !== sequence.current) return;
      if (ac.signal.aborted) return;
      setValidated(null);
      setWarnings([]);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Repositories could not be validated.",
      );
    } finally {
      if (token === sequence.current) setChecking(false);
    }
  }, []);

  // Debounced auto-validation once both fields are plausible.
  useEffect(() => {
    if (!ready) {
      setValidated(null);
      setError(null);
      setWarnings([]);
      return;
    }
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void validate(origin, target), DEBOUNCE_MS);
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
      if (response.warnings?.length) setWarnings((prev) => [...new Set([...prev, ...response.warnings])]);
      router.push(`/analysis/${response.job.job_id}`);
    } catch (err) {
      setStarting(false);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "The analysis could not be started.",
      );
    }
  }

  return (
    <div className="trace-panel" data-busy={starting}>
      <div className="trace-inputs">
        <RepoInput
          label="the repository you suspect"
          role="origin"
          value={origin}
          onChange={onOrigin}
          repository={(validated?.origin as RepositorySummary) ?? null}
          error={error && !validated ? error : null}
          checking={checking}
          disabled={starting}
        />
        <div className="trace-connector" aria-hidden="true">
          <span />
        </div>
        <RepoInput
          label="the repository to explain"
          role="target"
          value={target}
          onChange={onTarget}
          repository={(validated?.target as RepositorySummary) ?? null}
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

      {warnings.length > 0 ? (
        <ul className="trace-warnings" role="status">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}

      <div className="trace-actions">
        <button
          type="button"
          className="btn btn-primary btn-lg"
          onClick={() => void start()}
          disabled={!ready || starting}
          aria-describedby={!ready ? "trace-hint" : undefined}
        >
          {starting ? "Starting analysis…" : "Trace lineage"}
        </button>
        <p id="trace-hint" className="trace-hint">
          {!ready
            ? "Enter two repositories to begin."
            : validated
              ? "Both repositories are public and will be pinned to their current commit."
              : "ForkReason pins an immutable commit for each repository before analyzing."}
        </p>
      </div>
    </div>
  );
}