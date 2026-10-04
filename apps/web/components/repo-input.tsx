"use client";

import { useId } from "react";

import type { RepositorySummary } from "@/lib/api";
import { shortSha } from "@/lib/presentation";

/**
 * Repository input.
 *
 * Purely presentational: the parent owns validation because the API validates
 * the *pair*, not one side. This component renders the result, the reason a
 * pair failed, and the pinned commit that will actually be analyzed.
 *
 * Deliberately not auto-validating on every keystroke. The parent debounces.
 */
export function RepoInput({
  label,
  role,
  value,
  onChange,
  repository,
  error,
  checking,
  disabled,
}: {
  label: string;
  role: "origin" | "target";
  value: string;
  onChange: (value: string) => void;
  repository: RepositorySummary | null;
  error: string | null;
  checking: boolean;
  disabled?: boolean;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = error ? `${hintId} ${errorId}` : hintId;

  return (
    <div className="repo-input" data-role={role}>
      <div className="repo-input-head">
        <label htmlFor={id} className="repo-input-label">
          <span className="repo-input-role" data-role={role}>
            {role === "origin" ? "Origin" : "Target"}
          </span>
          <span className="repo-input-label-text">{label}</span>
        </label>
        <span className="repo-input-status" role="status" aria-live="polite">
          {checking ? "checking…" : repository ? "ready" : ""}
        </span>
      </div>

      <div className="repo-input-field" data-error={error ? "true" : "false"}>
        <span className="repo-input-prefix" aria-hidden="true">
          github.com/
        </span>
        <input
          id={id}
          className="repo-input-control"
          type="text"
          inputMode="url"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          placeholder="owner/repository"
          value={value}
          disabled={disabled}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          onChange={(event) => onChange(event.target.value)}
        />
        {repository ? (
          <span className="repo-input-ok" aria-hidden="true">
            ✓
          </span>
        ) : null}
      </div>

      <p id={hintId} className="repo-input-hint">
        Public GitHub repository — <code className="mono">owner/name</code> or a
        full URL.
      </p>

      {error ? (
        <p id={errorId} className="repo-input-error" role="alert">
          {error}
        </p>
      ) : null}

      {repository ? (
        <div className="repo-input-result">
          <div className="repo-input-result-main">
            <span className="repo-input-name mono">{repository.full_name}</span>
            {repository.is_fork ? <span className="badge badge-aqua">fork</span> : null}
            {repository.parent ? (
              <span className="badge badge-signal">upstream declared</span>
            ) : null}
          </div>

          <dl className="repo-input-meta">
            <div>
              <dt>Pinned commit</dt>
              <dd className="mono">{shortSha(repository.commit, 12)}</dd>
            </div>
            <div>
              <dt>Default branch</dt>
              <dd className="mono">{repository.default_branch}</dd>
            </div>
            <div>
              <dt>History</dt>
              <dd className="mono">
                {repository.recent_commits.length > 0
                  ? `${repository.recent_commits.length} recent`
                  : "unavailable"}
              </dd>
            </div>
            <div>
              <dt>Size</dt>
              <dd className="mono">{Math.max(1, Math.round(repository.size_bytes / 1024))} KB</dd>
            </div>
          </dl>

          {repository.description ? (
            <p className="repo-input-description">{repository.description}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}