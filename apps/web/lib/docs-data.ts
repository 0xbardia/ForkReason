/**
 * Documentation content as data.
 *
 * Deliberately free of React imports so it can be used from server components
 * (`generateStaticParams`, `generateMetadata`) as well as the client shell.
 */

export interface DocSection {
  title: string;
  href?: string;
  blurb?: string;
}

export interface DocBlock {
  kind: "p" | "h3" | "ul" | "ol" | "code" | "note" | "table" | "badge";
  text?: string;
  items?: string[];
  lang?: string;
  rows?: string[][];
  header?: string[];
  tone?: string;
}

export interface DocPage {
  slug: string;
  title: string;
  summary: string;
  blocks: DocBlock[];
}

const p = (text: string): DocBlock => ({ kind: "p", text });
const h3 = (text: string): DocBlock => ({ kind: "h3", text });
const ul = (...items: string[]): DocBlock => ({ kind: "ul", items });
const ol = (...items: string[]): DocBlock => ({ kind: "ol", items });
const code = (text: string, lang = "bash"): DocBlock => ({ kind: "code", text, lang });
const note = (text: string): DocBlock => ({ kind: "note", text });
const badge = (text: string, tone = "mint"): DocBlock => ({ kind: "badge", text, tone });
const table = (header: string[], rows: string[][]): DocBlock => ({ kind: "table", header, rows });

export const DOC_PAGES: DocPage[] = [
  {
    slug: "",
    title: "Overview",
    summary:
      "ForkReason reconstructs software lineage and records it through GenLayer consensus.",
    blocks: [
      p(
        "ForkReason answers one question well: given two repositories, what actually happened between them? It compares code, reconstructs chronology, evaluates the innocent explanations alongside the obvious one, and records the conclusion as an immutable revision.",
      ),
      h3("What ForkReason is"),
      ul(
        "A forensic pipeline that produces evidence, not a score.",
        "A verdict engine that is allowed to say \"insufficient evidence\".",
        "A record on GenLayer that anyone can check and anyone can challenge.",
      ),
      h3("What ForkReason is not"),
      ul(
        "Not a plagiarism detector. ForkReason never claims a repository was stolen, infringing, or illegal.",
        "Not a similarity search with a threshold. Matching code is the beginning of the question, not the answer.",
        "Not a legal instrument. It reports development relationships; it makes no legal determination.",
      ),
      badge("A boring, defensible result is a success."),
      h3("The core idea"),
      p(
        "Similarity is not lineage. Two files match for many uninteresting reasons: a shared framework, an implemented specification, a common upstream, or an unfashionable week in 2014. ForkReason only claims a lineage when chronology and historical evidence agree, and it always shows the evidence that argues the other way.",
      ),
    ],
  },
  {
    slug: "quickstart",
    title: "Quick start",
    summary: "Trace your first repository relationship.",
    blocks: [
      p("Paste two public GitHub repositories into the hero on the landing page, or go to Trace."),
      ol(
        "ForkReason validates both repositories and pins an immutable commit for each.",
        "Press **Trace lineage**. No wallet is required.",
        "Watch the eight pipeline stages complete. Each stage reflects real work.",
        "Open the case report to inspect the verdict, evidence, counter-evidence and every competing explanation.",
      ),
      h3("What to try first"),
      p(
        "A repository you know was forked from something, against its declared upstream parent. ForkReason should report DECLARED_FORK or SHARED_UPSTREAM.",
      ),
      code(
        "origin:  a project you suspect was derived from something\ntarget:  the same project on another account",
        "text",
      ),
    ],
  },
  {
    slug: "how-it-works",
    title: "How ForkReason works",
    summary: "The eight-stage pipeline, end to end.",
    blocks: [
      p(
        "Analysis runs in a durable worker, never inside an HTTP request. Each stage below is observable in the UI, and each one reflects work that actually happened.",
      ),
      table(
        ["Stage", "What it does"],
        [
          ["Repository snapshots", "Materialize the pinned commit with git archive. Never execute repository code."],
          ["Commit history", "Read chronology for both repositories. Establishes which came first."],
          ["Structural fingerprints", "Normalized token, structure and constant fingerprints across both trees."],
          ["Historical signals", "Bug, test, language and architecture layers, weighted by rarity."],
          ["Shared upstream", "Look for a plausible common ancestor, which must predate the later repository."],
          ["Alternative explanations", "Score every explanation, including the ones that exonerate."],
          ["Evidence manifest", "Build the canonical bounded manifest and hash it."],
          ["Consensus preparation", "Assemble the bounded digest a GenLayer validator will evaluate."],
        ],
      ),
      h3("Determinism"),
      p(
        "The same pinned commits and the same configuration produce a byte-identical evidence manifest, and therefore the same SHA-256 hash. Analysis is reproducible, which is what makes the hash worth recording.",
      ),
      h3("Bounded by construction"),
      p(
        "Every intake has explicit limits on repository size, file size, file count, history depth, evidence count and wall-clock time. A limit that truncates the inventory is reported to the user rather than hidden.",
      ),
    ],
  },
  {
    slug: "repo-dna",
    title: "Repo DNA",
    summary: "Six evidence layers and what each one can prove.",
    blocks: [
      p(
        "A repository is measured across six independent dimensions. No single layer can establish lineage; the combination is what discriminates copying from coincidence.",
      ),
      table(
        ["Layer", "Derives", "Why it matters"],
        [
          ["CODE", "Normalized structure, uncommon constants, ordered token sequences", "Constants and ordering survive refactors that rename everything."],
          ["ARCHITECTURE", "Directory topology, module boundaries, subsystem names", "The same decomposition implies the same thinking."],
          ["HISTORY", "Commit chronology, first occurrence, implementation order", "This is what turns similarity into direction."],
          ["BUG", "Shared defect signatures, fix timing, pre-fix behaviour", "Nobody independently writes the same unusual mistake twice."],
          ["TEST", "Distinctive test names, fixtures, regression scenarios", "Tests usually travel with the implementation they cover."],
          ["LANGUAGE", "Naming, comments, unusual terminology, doc phrasing", "Shared distinctive phrasing is hard to produce independently."],
        ],
      ),
      h3("Weak signals stay weak"),
      p(
        "Common framework vocabulary is discounted to nothing before it can become evidence. A match on import, def, class or self carries no lineage information, because every project in the language has them.",
      ),
      note(
        "This is enforced mechanically: structural and shingle comparisons filter the boilerplate set before scoring, so it is not a matter of tuning.",
      ),
    ],
  },
  {
    slug: "evidence-model",
    title: "Evidence model",
    summary: "How evidence is weighted, bounded and ranked.",
    blocks: [
      p(
        "Every evidence item is bound to a pinned commit, a file path, a bounded excerpt and a strength. Evidence without a source is not evidence.",
      ),
      h3("Weighting"),
      p(
        "Signals are weighted by rarity. A distinctive domain term outranks a common one; a longer compound token is less likely to collide by accident. Scores are bounded and are used to rank, never shown as a probability.",
      ),
      h3("Strength buckets"),
      ul(
        "HIGH — a signal that is both strong and rare.",
        "MEDIUM — a signal that is suggestive but has an innocent explanation.",
        "LOW — a signal that mostly indicates a shared ecosystem.",
      ),
      note(
        "ForkReason has no calibration methodology, so confidence is reported as a bucket and never as a probability. A number would imply a precision that does not exist.",
      ),
      h3("The manifest"),
      p(
        "The evidence manifest is the canonical, bounded set submitted to consensus. It contains the pinned repositories and commits, chronology facts, evidence items with strength, conflicting signals, every alternative explanation, and shared-upstream candidates. It is canonicalized (sorted keys, ordered collections, quantized numbers) before hashing.",
      ),
      code(
        "manifest_hash = SHA-256(canonical_json(manifest))",
        "text",
      ),
      p(
        "Anyone with the same two commits can recompute the hash and confirm nothing was altered between analysis and record.",
      ),
    ],
  },
  {
    slug: "verdicts",
    title: "Verdicts",
    summary: "The six outcomes ForkReason can reach, and what each means.",
    blocks: [
      table(
        ["Verdict", "Means"],
        [
          ["INDEPENDENT", "Similarity is consistent with two projects implementing the same specification, with no shared history found."],
          ["SHARED_UPSTREAM", "Both repositories descend from a common ancestor, which explains the overlap better than derivation does."],
          ["DECLARED_FORK", "One repository declares the other as its upstream. This is a recorded, legitimate relationship."],
          ["LIKELY_DERIVED", "Chronology and historical evidence support one repository developing from the other."],
          ["HEAVILY_DERIVED", "A real lineage, but the implementation has since diverged substantially."],
          ["INSUFFICIENT_EVIDENCE", "The available evidence does not support a conclusion either way."],
        ],
      ),
      h3("Direction"),
      p(
        "A directional verdict names which repository came from which. INDEPENDENT, SHARED_UPSTREAM, DECLARED_FORK and INSUFFICIENT_EVIDENCE have no direction, and the report says so rather than inventing one.",
      ),
      h3("Why insufficient evidence is a real answer"),
      p(
        "Most repository pairs that look similar are not related, and most pairs with real relationship have evidence that supports it. The honest middle is large. ForkReason returns INSUFFICIENT_EVIDENCE rather than picking the least-bad explanation, because a forced verdict is worse than no verdict.",
      ),
    ],
  },
  {
    slug: "lineage-timeline",
    title: "Lineage timeline",
    summary: "Why chronology decides direction.",
    blocks: [
      p(
        "The single most decisive fact in a lineage question is which repository existed first. This is why the timeline is rendered as a first-class part of every report.",
      ),
      h3("The rules, in code"),
      ol(
        "A target whose earliest commit predates the origin's cannot have been derived from it. Every origin-to-target explanation is ruled out, whatever the similarity scores say.",
        "A target that appeared only after the origin matured is *permissive*, not evidentiary. Two unrelated projects started a year apart look identical, so this signal is capped and cannot carry a verdict alone.",
        "A signal whose first occurrence predates the target's first commit is directional evidence. The reverse is not.",
      ),
      note(
        "These rules run in Python, not in model prose. A model cannot argue its way past them.",
      ),
      h3("Reading the timeline"),
      p(
        "Each commit marker is real: a SHA, a timestamp, an author and a message from the repository itself. Where a defect was introduced and later fixed is visible, because Bug DNA reads code at specific points in history rather than only at HEAD.",
      ),
    ],
  },
  {
    slug: "shared-upstream",
    title: "Shared upstream",
    summary: "Finding the common ancestor that explains an overlap.",
    blocks: [
      p(
        "Many pairs that look copied are two forks of a third project. ForkReason looks for that third project, and prefers it as an explanation when it fits better.",
      ),
      h3("How a candidate is found"),
      ol(
        "GitHub's own fork metadata. A declared parent outranks any heuristic, because it is a recorded fact rather than an inference.",
        "Distinctive module and content vocabulary shared by both sides, which survives a rename.",
        "An ancestry constraint: a candidate must have existed *before* the later of the two repositories. A common ancestor that appeared afterwards is not an ancestor.",
      ),
      h3("Why it wins when it fits"),
      p(
        "If a plausible ancestor explains the shared signals better than derivation does, the honest verdict is SHARED_UPSTREAM. Reporting LIKELY_DERIVED in that situation would be accusing a fork of something it did not do.",
      ),
    ],
  },
  {
    slug: "consensus",
    title: "GenLayer consensus",
    summary: "How a decision is reached, and why one model is not enough.",
    blocks: [
      p(
        "A lineage finding is a judgement about the past. Judgements that rest on one model reading two READMEs are not verifiable, so the decision goes through GenLayer's Equivalence Principle with independent validators.",
      ),
      h3("What is compared"),
      p("Only stable fields participate in the comparison:"),
      ul(
        "verdict",
        "confidence bucket",
        "direction",
        "shared upstream",
        "independent-origin plausibility",
        "strongest evidence classes",
      ),
      p(
        "Prose explanations are never compared for equality. Two validators can reach the same conclusion and describe it differently; that is agreement, not noise.",
      ),
      h3("What a validator actually does"),
      ol(
        "It receives the leader's result and the same bounded evidence digest.",
        "It independently derives its own decision, rather than re-parsing the leader's.",
        "It applies the deterministic guards to its own decision.",
        "It compares the stable field tuple of its decision against the leader's.",
      ),
      note(
        "A leader is never accepted because its output parses. A well-formed but substantively wrong verdict is rejected.",
      ),
      h3("Fail closed"),
      p(
        "If verification cannot complete, the case does not resolve as accepted. Unparseable output, an off-enum value, or a chronology contradiction all result in rejection rather than a default.",
      ),
      h3("No storage in nondeterministic execution"),
      p(
        "The nondeterministic block computes a decision and returns it. Contract state is written only afterwards, in deterministic execution, after consensus has accepted.",
      ),
    ],
  },
  {
    slug: "challenges",
    title: "Challenges & revisions",
    summary: "Contesting a finding produces a new revision, never an edit.",
    blocks: [
      p(
        "A conclusion that cannot be contested is not credible. Every resolved case can be challenged with new evidence.",
      ),
      h3("The lifecycle"),
      code(
        "SUBMITTED → CONSENSUS_PENDING → RESOLVED\nRESOLVED → CHALLENGED → CONSENSUS_PENDING → RESOLVED (revision N+1)",
        "text",
      ),
      h3("Revisions are append-only"),
      p(
        "A challenge creates revision N+1. Revision N is never overwritten or deleted, and both remain readable forever. The history is the point.",
      ),
      h3("Stale challenges are refused"),
      p(
        "A challenge must reference the current revision. A challenge racing another challenge is rejected rather than silently overwriting it.",
      ),
      h3("What a challenge needs"),
      ul(
        "A stated reason: what the analysis missed.",
        "Bounded supporting evidence: commits, paths, a declared parent.",
        "A wallet signature. ForkReason's server holds no key that can act for you.",
      ),
      note(
        "Challenge evidence is treated as inert data, exactly like everything else a repository contains.",
      ),
    ],
  },
  {
    slug: "contract",
    title: "Contract",
    summary: "ForkReasonRegistry methods and their bounds.",
    blocks: [
      p(
        "The GenLayer Intelligent Contract is written in Python using the current official SDK and retains its canonical dependency header.",
      ),
      code(
        '# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }',
        "python",
      ),
      h3("Writes"),
      ul(
        "submit_case(origin_repo, origin_commit, target_repo, target_commit, manifest_hash, evidence_digest)",
        "challenge_case(case_id, base_revision, challenge_rationale, evidence_digest)",
      ),
      h3("Reads"),
      ul(
        "get_case(case_id)",
        "get_case_count()",
        "get_latest_revision(case_id)",
        "get_revision(case_id, revision_number)",
        "get_revision_count(case_id)",
        "get_challenge(challenge_id)",
        "get_challenge_count(case_id)",
        "get_cases_page(offset, limit) — bounded pagination",
        "get_dna_layers(), get_valid_verdicts(), get_valid_confidences()",
      ),
      h3("Bounds"),
      p(
        "Every input is length-bounded, every enum is validated, duplicates and replays are refused, and stale-revision challenges are rejected. There is deliberately no unbounded \"return everything\" method.",
      ),
      h3("Verified surface"),
      p(
        "Direct Mode covers every public method, including bounds, duplicates, invalid enums, manifest hash, resolution, shared upstream, insufficient evidence, challenge, immutable revision, stale revision, malformed model result, web error, LLM error, validator disagreement, leader manipulation and prompt injection.",
      ),
    ],
  },
  {
    slug: "wallet",
    title: "Wallet transactions",
    summary: "What your wallet signs, and what it does not.",
    blocks: [
      p(
        "ForkReason never signs a transaction on your behalf. Reads require no wallet at all; writes require your own signature.",
      ),
      h3("What needs a wallet"),
      ul(
        "Recording a resolved case on chain.",
        "Submitting a challenge that produces a new revision.",
      ),
      h3("What does not"),
      ul(
        "Tracing a relationship.",
        "Reading any case report, evidence item or revision.",
        "Browsing Explore.",
      ),
      h3("The transaction lifecycle"),
      p(
        "ForkReason displays the real status from the GenLayer client. A transaction moves through submitted, awaiting decision, and then either accepted or failed.",
      ),
      note(
        "A decided transaction is not a successful one. The status ACCEPTED means the committee agreed on the receipt; ForkReason also requires a successful execution result before reporting success.",
      ),
      h3("Fee and rejection errors"),
      p(
        "A rejected transaction, an insufficient balance, and a wrong network each produce a specific, actionable message rather than a generic failure.",
      ),
    ],
  },
  {
    slug: "architecture",
    title: "Architecture",
    summary: "Three processes, one database, and a clear chain boundary.",
    blocks: [
      p("ForkReason runs as three durable processes:"),
      table(
        ["Process", "Responsibility"],
        [
          ["forkreason-web", "Next.js frontend. Renders the product surface."],
          ["forkreason-api", "FastAPI. Validation, job creation, case and evidence reads, chain read endpoints."],
          ["forkreason-worker", "Durable analysis worker. Runs the forensic pipeline outside any request."],
        ],
      ),
      h3("The job queue"),
      p(
        "Jobs live in PostgreSQL and are claimed with FOR UPDATE SKIP LOCKED. No Redis: the server already runs PostgreSQL, and one fewer broker is one fewer failure mode.",
      ),
      ul(
        "A crashed worker's job is recovered when its lease expires, because the lease is deliberately preserved on the failure path.",
        "Repeating failures are stopped rather than retried forever.",
        "Resubmitting the same pinned pair does not duplicate work: the idempotency key is unique.",
      ),
      h3("Data model"),
      ul(
        "RepositorySnapshot — an immutable pinned view at one commit.",
        "AnalysisJob — durable work with real stage states.",
        "Case — a pointer to the current revision number, never mutable verdict fields.",
        "CaseRevision — append-only, with a unique (case, revision) constraint.",
        "EvidenceItem, EvidenceRelation, AlternativeExplanation, Challenge, ChainTransaction.",
      ),
      h3("The chain boundary"),
      p(
        "The database indexes and caches chain state. It is never allowed to become the authority over on-chain revision or verdict state.",
      ),
    ],
  },
  {
    slug: "api",
    title: "API",
    summary: "Versioned endpoints under /api/v1.",
    blocks: [
      table(
        ["Endpoint", "Purpose"],
        [
          ["POST /api/v1/repositories/validate", "Validate both repositories and pin their commits."],
          ["POST /api/v1/analyses", "Create a durable analysis for a pinned pair."],
          ["GET /api/v1/analyses/{id}", "Real pipeline progress. No invented percentages."],
          ["POST /api/v1/analyses/{id}/cancel", "Request cancellation at a stage boundary."],
          ["GET /api/v1/analyses/{id}/manifest", "The canonical evidence manifest."],
          ["GET /api/v1/cases", "Bounded pagination over public cases."],
          ["GET /api/v1/cases/{id}", "The full case report."],
          ["GET /api/v1/cases/{id}/evidence", "Filterable evidence with facets."],
          ["POST /api/v1/cases/{id}/challenge-preparation", "Prepare a payload for the user's wallet to sign."],
          ["GET /api/v1/search", "Search by repository, case id or verdict."],
          ["GET /api/v1/chain/contract", "Where the registry lives, and what it can do."],
          ["GET /health, GET /ready", "Liveness and readiness."],
        ],
      ),
      h3("Conventions"),
      ul(
        "Errors return a stable code and a readable message. Stack traces never cross the boundary.",
        "Pagination is bounded on every list endpoint.",
        "Request validation failures name the fields, never the values.",
      ),
    ],
  },
  {
    slug: "testing",
    title: "Testing",
    summary: "Fixtures, gates and what each one proves.",
    blocks: [
      h3("Fixture scenarios"),
      table(
        ["Scenario", "Expected"],
        [
          ["A · real derivation with rename and refactor", "LIKELY_DERIVED or HEAVILY_DERIVED"],
          ["B · both sides derive from one upstream", "SHARED_UPSTREAM"],
          ["C · independent implementations of one spec", "INDEPENDENT or INSUFFICIENT_EVIDENCE"],
          ["D · not enough history", "INSUFFICIENT_EVIDENCE"],
          ["E · prompt-injection repository", "malicious instructions ignored"],
          ["F · declared legitimate fork", "DECLARED_FORK"],
          ["G · conflicting evidence changes the verdict", "revision preserved, new verdict"],
        ],
      ),
      h3("Contract tests"),
      p(
        "Direct Mode runs the contract natively with mocks for the model and web calls. It covers every public method, and the tests that matter most are the adversarial ones: a leader returning a well-formed but substantively wrong verdict must be rejected, and the same malicious payload reaching every validator context must not change the outcome.",
      ),
      h3("Studio Mode"),
      p(
        "Studio Mode runs real multi-validator consensus rather than mocks. It is not a substitute for Direct Mode; it verifies that the consensus path works against real validators.",
      ),
      h3("Browser QA"),
      p(
        "Release-critical flows are tested on Chromium, Firefox and WebKit across desktop, tablet and 390/360/320px widths, asserting no console errors, no unhandled rejections, no 5xx, no hydration errors, no horizontal overflow, and reduced-motion support.",
      ),
    ],
  },
  {
    slug: "deployment",
    title: "Deployment",
    summary: "Running ForkReason yourself.",
    blocks: [
      h3("Requirements"),
      ul(
        "Python 3.12+, Node.js 20+",
        "PostgreSQL 14+",
        "Docker, only if you want Studio Mode locally",
      ),
      h3("Backend"),
      code(
        "uv venv --python 3.12 .venv\nuv pip install --python .venv/bin/python -r requirements-api.txt\ncp .env.example .env   # then edit DATABASE_URL\n.venv/bin/python -m alembic upgrade head",
        "bash",
      ),
      h3("Processes"),
      code(
        "# API\nPYTHONPATH=apps/api .venv/bin/python -m uvicorn forkreason.main:app --host 127.0.0.1 --port 8421\n\n# worker\nPYTHONPATH=apps/api .venv/bin/python -m forkreason.jobs.runner",
        "bash",
      ),
      h3("Frontend"),
      code("cd apps/web && npm ci && npm run build && npm start", "bash"),
      h3("In front of nginx"),
      p(
        "Serve the frontend and proxy /api to the API process. Terminate TLS, redirect HTTP to HTTPS, set security headers, and let the Next middleware handle the CSP with its per-request nonce.",
      ),
      note(
        "The API and worker must be separate durable processes. Analysis belongs in the worker, never in a request.",
      ),
    ],
  },
  {
    slug: "open-source",
    title: "Open source",
    summary: "Repository, license and how to contribute.",
    blocks: [
      p("ForkReason's source is public so that its evidence can be audited."),
      code("https://github.com/0xbardia/ForkReason", "text"),
      h3("License"),
      p(
        "AGPL-3.0. The copyleft matters here: a forensic tool that claims to be verifiable should not be forkable into something unverifiable.",
      ),
      h3("What to check"),
      ul(
        "The forensic pipeline is plain Python with no model dependency in the decision logic.",
        "The evidence model and scoring are deterministic and unit-tested.",
        "The contract is a single readable Python file with a Direct Mode suite.",
        "The adversarial fixtures are committed, not described.",
      ),
      h3("Contributing"),
      p(
        "Bug fixes and additional fixture scenarios are the most useful contributions. A pull request that changes scoring should include the fixture scenario it was tuned against.",
      ),
    ],
  },
  {
    slug: "prompt-injection",
    title: "Prompt injection",
    summary: "Why consensus does not save you, and what ForkReason does instead.",
    blocks: [
      p(
        "This is the most important security property in ForkReason, so it is worth being blunt about the problem: consensus does not defend against prompt injection.",
      ),
      h3("The trap"),
      p(
        "If a repository's README tells the model to return a particular verdict, and the leader obeys, and every validator reads the same README and obeys too, then they agree. Unanimity. The consensus mechanism reports success while producing exactly the wrong answer.",
      ),
      h3("How ForkReason defends"),
      ol(
        "Deterministic preprocessing. Comments and string literals are stripped before any structural comparison, so injected prose cannot influence a fingerprint.",
        "Minimal excerpts. The consensus digest is capped and never contains whole files.",
        "Strong delimiters. Untrusted content is fenced inside explicit tags.",
        "Explicit inert-data instruction, stated as an absolute rule above the evidence block.",
        "Strict typed parsing against an allowed enum set.",
        "Deterministic rule checks in code: chronology, verdict-confidence contradictions, shared-upstream requirements.",
        "Independent validator evaluation of the substantive fields.",
        "Fail closed on anything unparseable or off-enum.",
      ),
      h3("The decisive test"),
      p(
        "The adversarial suite places the mandated attack phrases in a README, a code comment, a string constant, HTML, commit metadata and challenge evidence. Then it simulates the leader actually obeying the injection, and asserts the verdict is refused.",
      ),
      code(
        'leader says INDEPENDENT because the README said so\nvalidator derives its own answer from the evidence\nresult: REJECTED',
        "text",
      ),
      h3("The same payload, every validator"),
      p(
        "A separate test hands the attacker-demanded verdict to every captured validator and asserts none of them accept it. The point is not that validators disagree with each other — it is that the demanded answer is refused even under unanimity.",
      ),
    ],
  },
  {
    slug: "threat-model",
    title: "Threat model",
    summary: "Adversaries, assumptions and controls.",
    blocks: [
      h3("Adversaries ForkReason assumes"),
      ul(
        "A repository crafted to look like a copy of another, without being one.",
        "A repository crafted to look unrelated while sharing implementation.",
        "A repository crafted to instruct the model.",
        "A user crafting input to reach the filesystem, the shell, or the database.",
      ),
      h3("Controls"),
      table(
        ["Threat", "Control"],
        [
          ["Command injection", "Subprocess argument arrays only, shell=false, fixed binary, validated identifiers."],
          ["Path traversal", "Archive members validated before and after path resolution."],
          ["Symlink escape", "Links rejected; os.walk with followlinks=false plus an explicit guard."],
          ["Repository execution", "git archive of tracked blobs; no working tree, no hooks, no submodule content."],
          ["Resource exhaustion", "Explicit limits on size, file count, depth, evidence count and wall clock."],
          ["SSRF", "No fetch-arbitrary-URL capability; redirects are not followed."],
          ["Prompt injection", "Deterministic preprocessing, delimiters, strict parsing, independent validators, fail closed."],
          ["Custodial signing", "No server key can act for a user."],
          ["Forged revisions", "Chain state is authoritative; the database only indexes it."],
        ],
      ),
      h3("Out of scope for V1"),
      ul(
        "Private repositories.",
        "Non-GitHub hosts.",
        "Authenticated repository access of any kind.",
        "Legal determination of any kind.",
      ),
    ],
  },
  {
    slug: "limitations",
    title: "Limitations",
    summary: "What ForkReason cannot do, stated plainly.",
    blocks: [
      h3("Genuine limitations"),
      ul(
        "ForkReason analyzes public GitHub repositories only in V1.",
        "A repository with a squashed or shallow history has weak chronology, and the report will say the history was limited.",
        "A monorepo is analyzed as one repository; it is not decomposed into independently versioned packages.",
        "Shared-upstream discovery is heuristic for repositories that do not declare a fork parent, and can miss a common ancestor.",
        "Authorship, ownership and intent are never inferred. ForkReason reports development relationships, not who wrote what or why.",
        "Gencode, minified output and vendored trees are inventoried but not analyzed, because they carry no authorship signal.",
      ),
      h3("Deliberate non-goals"),
      ul(
        "No legal conclusions. ForkReason never says a repository was stolen or infringing.",
        "No ownership verification.",
        "No blame. A finding describes a relationship, not a person.",
        "No confidence percentages, because there is no calibration methodology.",
      ),
      note(
        "A tool that claims to measure provenance honestly has to state where it is not measuring it.",
      ),
    ],
  },
  {
    slug: "faq",
    title: "FAQ",
    summary: "Common questions, answered without hedging.",
    blocks: [
      h3("Does ForkReason tell me if a repository was stolen?"),
      p(
        "No. ForkReason reports development lineage: whether one repository appears to derive from another, share an upstream, or have no detectable relationship. Those are not legal conclusions and ForkReason does not make them.",
      ),
      h3("Why does it often say INSUFFICIENT_EVIDENCE?"),
      p(
        "Because most similar-looking repository pairs are not related, and a large fraction of real relationships do not leave enough trace to distinguish from coincidence. Returning a verdict in those cases would make the tool worse, not better.",
      ),
      h3("Do I need a wallet?"),
      p("Only to record a finding on chain or submit a challenge. Analysis and every read are free and walletless."),
      h3("Is my repository data sent anywhere?"),
      p(
        "Snapshots are written to disk on the ForkReason server for analysis. Only a bounded evidence digest goes to a model for the decision, and never a whole repository. Nothing is sent to a third party beyond the GenLayer network if you choose to record a result.",
      ),
      h3("Can a malicious repository manipulate the verdict?"),
      p(
        "It can try. That is why adversarial fixtures are part of the release gate, and why validators independently re-derive the decision instead of trusting the leader.",
      ),
      h3("How long does an analysis take?"),
      p(
        "It depends on repository size, and ForkReason does not pretend to predict it. The progress view shows which stage is running and how long it has actually been running.",
      ),
    ],
  },
];

export function findDocPage(slug: string): DocPage | undefined {
  return DOC_PAGES.find((page) => page.slug === slug);
}

export const DOC_INDEX: Record<string, DocSection> = Object.fromEntries(
  DOC_PAGES.map((page) => [
    page.slug,
    { title: page.title, href: page.slug ? `/docs/${page.slug}` : "/docs" },
  ]),
);
