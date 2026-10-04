/**
 * Typed client for the ForkReason API.
 *
 * Every response is validated at the boundary before it reaches a component:
 * a malformed or hostile payload must not become an unhandled runtime error
 * deep in the render tree. `ApiClientError` carries the server's stable code so
 * the UI can branch on it instead of matching message strings.
 */

/**
 * In production the API is same-origin: nginx proxies /api to the API process,
 * so an empty base means "call /api/v1/...". That is also the CSP-safe choice,
 * because the browser then needs no cross-origin grant at all.
 *
 * The dev fallback only applies when running outside production, so a
 * production bundle can never bake a localhost origin into client JavaScript.
 */
const configured = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");

export const API_URL =
  configured && configured.length > 0
    ? configured
    : process.env.NODE_ENV === "production"
      ? ""
      : "http://localhost:8421";

export class ApiClientError extends Error {
  readonly code: string;
  readonly status: number;
  readonly fields?: string[];

  constructor(status: number, code: string, message: string, fields?: string[]) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
    this.fields = fields;
  }

  /** True when the failure is a connectivity problem, not an API rejection. */
  get isNetwork(): boolean {
    return this.code === "network_unreachable" || this.code === "timeout";
  }

  get isRateLimited(): boolean {
    return this.status === 429;
  }
}

const REQUEST_TIMEOUT_MS = 45_000;

async function request<T>(
  path: string,
  init: RequestInit & { signal?: AbortSignal } = {},
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...init,
      signal: init.signal ?? controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(init.headers ?? {}),
      },
      cache: "no-store",
    });

    if (response.status === 204) {
      return undefined as T;
    }

    const text = await response.text();
    let payload: unknown = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = null;
      }
    }

    if (!response.ok) {
      const error = (payload as { error?: Record<string, unknown> } | null)?.error;
      throw new ApiClientError(
        response.status,
        typeof error?.code === "string" ? error.code : "http_error",
        typeof error?.message === "string"
          ? error.message
          : `Request failed (${response.status}).`,
        Array.isArray(error?.fields) ? (error.fields as string[]) : undefined,
      );
    }

    return payload as T;
  } catch (error) {
    if (error instanceof ApiClientError) {
      throw error;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiClientError(
        408,
        "timeout",
        "The request took too long. The analysis may still be running — try refreshing.",
      );
    }
    throw new ApiClientError(
      0,
      "network_unreachable",
      "ForkReason's analysis service is unreachable. Check your connection and try again.",
    );
  } finally {
    clearTimeout(timeout);
  }
}

// --- response shapes ------------------------------------------------------

export type Verdict =
  | "INDEPENDENT"
  | "SHARED_UPSTREAM"
  | "DECLARED_FORK"
  | "LIKELY_DERIVED"
  | "HEAVILY_DERIVED"
  | "INSUFFICIENT_EVIDENCE";

export type Confidence = "LOW" | "MEDIUM" | "HIGH";
export type Direction = "ORIGIN_TO_TARGET" | "TARGET_TO_ORIGIN" | "NONE";
export type DnaLayer = "CODE" | "ARCHITECTURE" | "HISTORY" | "BUG" | "TEST" | "LANGUAGE";
export type StageState = "pending" | "working" | "complete" | "failed";

export interface RepositorySummary {
  full_name: string;
  canonical_url: string;
  commit: string;
  default_branch: string;
  description: string;
  is_fork: boolean;
  parent: string | null;
  pushed_at: number | null;
  size_bytes: number;
  recent_commits: Array<{
    sha: string;
    short_sha: string;
    message: string;
    date: string;
    author: string;
  }>;
  analyzable: boolean;
  note: string | null;
}

export interface ValidateResponse {
  origin: RepositorySummary;
  target: RepositorySummary;
  warnings: string[];
}

export interface StageView {
  name: string;
  state: StageState;
}

export interface AnalysisJob {
  job_id: string;
  status: string;
  stage: string;
  stages: StageView[];
  stages_complete: number;
  stages_total: number;
  case_id: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  origin: { repo: string; commit: string };
  target: { repo: string; commit: string };
  cancel_requested: boolean;
}

export interface CreateAnalysisResponse {
  job: AnalysisJob;
  created: boolean;
  idempotent_replay: boolean;
  warnings: string[];
  origin: { repo: string; commit: string; files: number; commits: number; truncated: boolean };
  target: { repo: string; commit: string; files: number; commits: number; truncated: boolean };
}

export interface EvidenceRef {
  repo?: string;
  commit?: string;
  path?: string | null;
}

export interface EvidenceCard {
  id: string;
  dna_layer: DnaLayer;
  evidence_type: string;
  is_conflicting: boolean;
  strength: Confidence;
  score: number;
  rationale: string;
  origin: EvidenceRef;
  target: EvidenceRef;
  excerpt: string | null;
}

export interface Explanation {
  kind: string;
  support: Confidence;
  score: number;
  rationale: string;
  is_selected: boolean;
}

export interface GraphEdge {
  id: string;
  subject_kind: string;
  subject_ref: string;
  relation: string;
  object_kind: string;
  object_ref: string;
  weight: number;
}

export interface RevisionView {
  revision_number: number;
  verdict: Verdict;
  confidence: Confidence;
  direction: Direction | null;
  shared_upstream: string | null;
  manifest_hash: string;
  tx_hash: string | null;
  created_at: string | null;
  is_current: boolean;
}

export interface CaseReport {
  case: {
    id: string;
    origin_repo: string;
    target_repo: string;
    origin_commit: string;
    target_commit: string;
    manifest_hash: string;
    current_revision: number;
    lifecycle: string;
    created_at: string | null;
  };
  verdict: {
    verdict: Verdict;
    confidence: Confidence;
    direction: Direction | null;
    shared_upstream: string | null;
    independent_origin_plausibility: Confidence | null;
    summary: Record<string, unknown> | null;
    rationale: string | null;
    revision_number: number;
    tx_hash: string | null;
    network: string | null;
  };
  evidence: EvidenceCard[];
  conflicting_evidence: EvidenceCard[];
  alternative_explanations: Explanation[];
  graph: GraphEdge[];
  revisions: RevisionView[];
}

export interface CaseCard {
  id: string;
  origin_repo: string;
  target_repo: string;
  verdict: Verdict | null;
  confidence: Confidence | null;
  direction: Direction | null;
  revision: number;
  lifecycle: string;
  manifest_hash: string;
  created_at: string | null;
}

export interface PagedCases {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  items: CaseCard[];
}

export interface ChallengePreparation {
  challenge_id: string;
  case_id: string;
  base_revision: number;
  expected_revision: number;
  evidence_digest: string;
  evidence_digest_sha256: string;
  chain: {
    network: string;
    rpc_url: string;
    contract_address: string | null;
  };
  write: {
    contract: string;
    method: string;
    args: unknown[];
    requires_wallet_signature: boolean;
  };
  next_step: string;
}

export interface ContractInfo {
  name: string;
  network: string;
  rpc_url: string;
  address: string | null;
  deployed: boolean;
  source_sha256: string | null;
  read_methods: string[];
  write_methods: string[];
  note: string;
}

// --- endpoints ------------------------------------------------------------

export const api = {
  validateRepositories(origin: string, target: string, signal?: AbortSignal) {
    return request<ValidateResponse>("/api/v1/repositories/validate", {
      method: "POST",
      body: JSON.stringify({ origin, target }),
      signal,
    });
  },

  createAnalysis(origin: string, target: string, signal?: AbortSignal) {
    return request<CreateAnalysisResponse>("/api/v1/analyses", {
      method: "POST",
      body: JSON.stringify({ origin, target }),
      signal,
    });
  },

  getAnalysis(jobId: string, signal?: AbortSignal) {
    return request<AnalysisJob>(`/api/v1/analyses/${encodeURIComponent(jobId)}`, {
      signal,
    });
  },

  cancelAnalysis(jobId: string) {
    return request<AnalysisJob>(`/api/v1/analyses/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST",
    });
  },

  getCase(caseId: string, signal?: AbortSignal) {
    return request<CaseReport>(`/api/v1/cases/${encodeURIComponent(caseId)}`, { signal });
  },

  getEvidence(
    caseId: string,
    params: { layer?: string; strength?: string; limit?: number; offset?: number } = {},
    signal?: AbortSignal,
  ) {
    const query = new URLSearchParams();
    if (params.layer) query.set("layer", params.layer);
    if (params.strength) query.set("strength", params.strength);
    if (params.limit) query.set("limit", String(params.limit));
    if (params.offset) query.set("offset", String(params.offset));
    const qs = query.toString();
    return request<{
      total: number;
      limit: number;
      offset: number;
      has_more: boolean;
      facets: { layers: Record<string, number>; strengths: Record<string, number> };
      items: EvidenceCard[];
    }>(
      `/api/v1/cases/${encodeURIComponent(caseId)}/evidence${qs ? `?${qs}` : ""}`,
      { signal },
    );
  },

  listCases(params: { limit?: number; offset?: number } = {}, signal?: AbortSignal) {
    const query = new URLSearchParams();
    query.set("limit", String(params.limit ?? 20));
    query.set("offset", String(params.offset ?? 0));
    return request<PagedCases>(`/api/v1/cases?${query.toString()}`, { signal });
  },

  search(
    params: { q?: string; verdict?: string; limit?: number; offset?: number } = {},
    signal?: AbortSignal,
  ) {
    const query = new URLSearchParams();
    if (params.q) query.set("q", params.q);
    if (params.verdict) query.set("verdict", params.verdict);
    query.set("limit", String(params.limit ?? 20));
    query.set("offset", String(params.offset ?? 0));
    return request<PagedCases>(`/api/v1/search?${query.toString()}`, { signal });
  },

  prepareChallenge(
    caseId: string,
    body: { rationale: string; evidence_summary: string; submitter: string },
  ) {
    return request<ChallengePreparation>(
      `/api/v1/cases/${encodeURIComponent(caseId)}/challenge-preparation`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  markChallengeSubmitted(caseId: string, challengeId: string, txHash: string) {
    return request<{ challenge_id: string; tx_hash: string; status: string }>(
      `/api/v1/cases/${encodeURIComponent(caseId)}/challenges/${encodeURIComponent(challengeId)}/submitted`,
      { method: "POST", body: JSON.stringify({ tx_hash: txHash }) },
    );
  },

  getContractInfo(signal?: AbortSignal) {
    return request<ContractInfo>("/api/v1/chain/contract", { signal });
  },
};