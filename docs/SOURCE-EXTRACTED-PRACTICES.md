# Source-extracted engineering practices

Extracted 2026-10-03 from six sources. Every claim below is traceable to a fetched
source; Playwright API facts were verified against the locally installed
`playwright@1.62.1` type definitions rather than the docs site (see Provenance).

---

## 1. OpenAI — "Rethinking skills and prompts for GPT-6 Astra"

Canonical: `https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra`
Author Eric Provencher, dated Sep 11 2026. (Markdown version: append `.md` to the URL.)

Core thesis: accumulated agent instructions are now mostly **negative-value**.
Audit and delete, do not add.

### Actionable

1. **Skill descriptions: shortest possible, trigger-scoped.** Trigger over-emphasis
   causes wrong-skill loading.
   - Bad: `Create and validate Postgres schema migrations. Use when working with databases, queries, models, or persistence.`
   - Good: `Create and validate Postgres schema migrations. Use when adding or changing a migration, or reviewing its rollout.`
2. **Progressive disclosure.** Root `SKILL.md` = minimal router pointing at
   `references/`, `scripts/`, `assets/`. Give enough guidance to know where to
   look without forcing a read of irrelevant files.
3. **Delete itinerary-style skills.** Elaborate step-by-step recipes now *hurt* —
   models infer process. Over-specified guidance over-constrains.
4. **AGENTS.md must be re-audited per release.** Point to docs *contextually*, never
   unconditionally.
   - Bad: `Before every edit, read architecture.md, database.md, and deployment.md.`
   - Good: `Use architecture.md for service boundaries, database.md for schema changes, and deployment.md when preparing a deployment.`
5. **Drop stale "always test" instructions.** Astra runs tests unprompted; the old
   line causes *unnecessary* testing. Replace with a scoped grant instead.
6. **Audit model-specificity.** Guidance tuned for Sol/Luna can over-constrain Astra.
   Repo skills also drive *other* contributors' agents on different models.
7. **Soften over-tight decision boundaries.** Boundary language added to stop an
   earlier model from overreaching can make Astra halt where you want continuation.
8. **Define completion explicitly.** Astra is thorough but stops early — it will
   return for review mid-task. Encode run + inspect + fix into the request itself.
   `A requirement to stop for review after the first implementation will pull the model toward an earlier stopping point.`
9. **Delegate the audit.** OpenAI's own advice: ask Astra to audit its instructions
   against this article rather than reviewing everything by hand.

---

## 2. AceCloud — "GPT-6 Astra: 22 Hacks and Prompts to Try"

Third-party, 22 numbered prompts, updated Sep 17 2026. Not authoritative; treat
as a prompt library. The reusable parts are the **structural blocks**.

### Actionable

- **Outcome brief** (Prompt 01): `Goal / Audience / Context / Constraints / Success looks like`,
  plus `If something important is missing, ask me. Otherwise, make reasonable assumptions and continue.`
- **Autonomy rules** (02): act autonomously on reversible work; approval is the
  *final* step for publish/merge/deploy/external writes, not an early interrupt.
- **Proportional testing** (03, 11): `Test only the affected functionality. Run broader
  checks only if the change, a failure, or an unresolved concern justifies them.`
  Plus a fixed close-out report: *what changed / what was checked / what passed /
  what could not be verified*.
- **Pre-authorised safe workflow** (04) — near-verbatim match to OpenAI's AGENTS.md
  example. Local dev only, disposable fixtures, no prod, no user data, stop before
  destructive/irreversible/external.
- **Anti-overengineering** (10): smallest maintainable change; check for an existing
  pattern first; no new dependency unless genuinely necessary; explain architectural
  change before making it; don't redesign unrelated code.
- **Skill-conflict forensics** (12): when the agent halts, require the exact
  `SKILL.md` path, the quoted line, and separation of explicit requirement vs. interpretation.
- **Instruction-file audit** (13): enumerate `AGENTS.md` / `SKILL.md`, find
  contradictions and rules that cause pausing or over-testing, propose a priority
  order, **do not modify until approved**.
- **Delegation rules** (14): delegate only clearly-scoped, independently-verifiable,
  parallelisable work; retain ownership of the final result.
- **Destructive-action gates** (19): prepare fully, show exactly what happens, name
  affected records, then wait.
- **Reasoning effort**: five levels `low|medium|high|xhigh|max`; pick lowest likely to
  work; fix the prompt before escalating effort.
- **Cost**: chunk at the **272K input-token** threshold (higher tier above it); set
  explicit output budgets and rank required sections.
- **Anti-slop blocklist** (06): `delve, foster, leverage, it's worth noting, genuinely,
  "This isn't about X. It's about Y."`, "Bottom Line:", contrastive `X, not Y` framing.
- **Frontend QA report format** (17): severity, exact location, repro steps,
  expected vs actual — and *don't fix unless asked*.

---

## 3. ParthSkills — "GPT-6 Astra Prompting Guide"

Third-party, Sep 8 2026. Independently corroborates AceCloud's behaviour claims.

### Actionable

- **8-part framework**: Goal / Context / Inputs / Constraints / Tools & Actions /
  Output / Verification / **Done Condition**. Use only the parts that help.
- **Behaviour deltas vs GPT-5.6 Sol**: asks clarifying questions more often when a gap
  could *materially* change the outcome; **more sensitive to files and skills**; tends
  toward structured/detailed output; needs explicit parallel-delegation instruction;
  may over-test small coding tasks.
- **Precedence rule for conflicts**: `prioritize the most specific current project
  requirement unless a higher-priority instruction prevents it.`
- **Bug-fix prompt**: reproduce → root cause → grep nearby code for related
  assumptions → smallest robust fix; preserve backward compat; add a test only when it
  meaningfully protects the corrected behaviour. Close out with root cause / files
  changed / fix / validation / remaining risks.
- **Reviewer prompt**: rank correctness, security, data-loss risk, race conditions,
  backward compat, error handling, real perf regressions. Don't report style
  preferences as defects. **`If you find no meaningful issues, say so rather than inventing findings.`**
- **Proportional testing** (small localized vs broad/high-risk), plus:
  `Do not repeatedly rerun unchanged tests after they have already passed unless new code changes require it.`
- **Don't ask for step-by-step reasoning** — ask for the result, evidence, assumptions
  and verification instead. Produces auditable output.
- **Useful vs unhelpful context** — supply what *changes the answer*; drop repeated
  versions, conflicting format rules, stale instructions, and role-play language that
  doesn't change the result.
- **API specifics** (third-party claim, verify before use): model id `gpt-6-astra`,
  ~1.05M context, up to 128K output, `low|medium|high|xhigh|max`, Responses API
  recommended for tool calling.

---

## 4. github/spec-kit — CURRENT CLI and phase commands

Canonical docs: `https://github.github.io/spec-kit/` · source: `github/spec-kit` main.
Verified against `README.md`, `docs/installation.md`, `docs/install/one-time.md`,
`reference/overview.html`, `reference/agentic-sdd.html`, and the repo tree + CLI source.

### ⚠️ The invocation model changed

Older guidance (`uvx --from git+... specify <phase> ...` run as terminal slash
commands per phase) is **no longer how phases run.** The `/speckit.*` entries are
**agent skills invoked in the agent's chat, one at a time** — explicitly *not* terminal
commands. The terminal `specify` binary does init and package management only.

`uvx --from git+https://github.com/github/spec-kit.git specify ...` is still valid, but
**only for `init`** — it is the one-time-usage route, not the phase runner.

### Install / init (terminal)

```bash
# Persistent, from source, pinned to a release tag — RECOMMENDED (keep leading v)
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@vX.Y.Z

# Persistent, from PyPI
uv tool install specify-cli          # or: pipx install specify-cli / pip install specify-cli

# One-time / throwaway — the only supported uvx surface
uvx --from git+https://github.com/github/spec-kit.git specify init <PROJECT_NAME>
uvx --from git+https://github.com/github/spec-kit.git@vX.Y.Z specify init <PROJECT_NAME>
uvx --from git+https://github.com/github/spec-kit.git specify init . --integration copilot
uvx --from git+https://github.com/github/spec-kit.git specify init --here --integration copilot
```

```bash
specify init <PROJECT_NAME> --integration <key>   # claude|copilot|gemini|codebuddy|pi|omp|hermes|...
specify init <PROJECT_NAME> --script sh|ps|py     # script variant
specify init my-project --non-interactive --ignore-agent-tools   # CI
specify init --here --force --non-interactive --integration claude
specify version          # runtime sanity check
specify self check       # read-only "is a newer release out?"
```

- Prereqs: Python 3.11+, uv (or pipx), supported agent. Linux/macOS/Windows.
- `--integration` defaults to **copilot** in non-interactive/CI runs.
- **Hermes integration exists** (`--integration hermes`, key `hermes` in
  `src/specify_cli/integrations/hermes/`): installs skills **globally** to
  `~/.hermes/skills/speckit-<name>/SKILL.md`, creates an empty project-local
  `.hermes/skills/` marker so extension commands can detect the active integration.
- This workspace is already initialized (`.specify/` present).

### Phase commands — agent skills, not terminal commands

Canonical order:

```
/speckit.constitution -> /speckit.specify -> /speckit.clarify -> /speckit.plan
  -> /speckit.checklist -> /speckit.tasks -> /speckit.analyze
  -> /speckit.implement -> /speckit.converge
```

| Slash form | Skill name (Hermes/Codex style) | Purpose | Required? |
|---|---|---|---|
| `/speckit.constitution` | `speckit-constitution` | Establish/update project principles | once per project |
| `/speckit.specify` | `speckit-specify` | Requirements + user stories (what/why) | **only hard requirement** |
| `/speckit.clarify` | `speckit-clarify` | Up to 5 targeted questions, writes answers back to `spec.md` | optional gate |
| `/speckit.plan` | `speckit-plan` | Technical plan (how: stack, architecture) | required |
| `/speckit.checklist` | `speckit-checklist` | "unit tests for your requirements" | optional gate |
| `/speckit.tasks` | `speckit-tasks` | Dependency-ordered `tasks.md` | required |
| `/speckit.analyze` | `speckit-analyze` | **Read-only** cross-artifact consistency report | optional gate |
| `/speckit.implement` | `speckit-implement` | Execute tasks in dependency order | required |
| `/speckit.converge` | `speckit-converge` | Assess code vs artifacts; **append-only** | required |
| `/speckit.taskstoissues` | `speckit-taskstoissues` | `tasks.md` → GitHub issues | optional |

**Answering the direct questions:**

- `checklist` command: **yes, it exists** — `/speckit.checklist` / `speckit-checklist`.
- `clarify`: exists. Formerly `/quizme`.
- `converge`: exists — the newest phase and the loop terminator.
- Template files on main: `analyze.md`, `checklist.md`, `clarify.md`,
  `constitution.md`, `converge.md`, `implement.md`, `plan.md`, `specify.md`,
  `tasks.md`, `taskstoissues.md`.

### Invocation syntax varies by agent

Copilot default (skills mode) uses `/speckit-*`; Codex/ZCode use `$speckit-*`;
Kimi uses `/skill:speckit-*`; docs use `/speckit.*`. Optional skills mode is selected
with `--integration-options="--skills"`; some integrations (Copilot) default to it.

### Hard process rules worth stealing even outside spec-kit

1. **Loop `implement → converge` until converge reports `Converged`.** Converged is the
   only exit. Anything else appends new tasks under a Convergence section and you re-run.
2. **Checklists are reviewer-owned.** In a custom checklist `[x]` means the reviewer
   judged the *requirement* satisfied — **not** that implementation is done.
3. **`implement` must never edit checklist markers.** It reads state as a gate, asks when
   items are unchecked, and leaves markers alone.
4. **`analyze` never edits files.** Report-only; fix at the source (specify/clarify for
   requirements, plan for design, tasks to regenerate) and re-run until clean.
5. **Constitution runs once up front**, updated when principles change; later phases are
   evaluated against it.
6. **Refine existing Markdown artifacts directly** instead of regenerating whole stages.
7. **Bug fixing and idea assessment are opt-in extensions**, not mandatory phases:
   `specify extension add bug` → `assess → fix → test` (verdict must be
   `verified`/`partial`/`failed`; `Missing verification is not a successful fix`);
   `specify extension add assess` → `intake → research → define → shape → decide`
   (go / needs-clarification / kill).
8. **Stage large features** — `/speckit.implement Implement only the Setup and
   Foundational phases… Stop before the user-story features.`

---

## 5. DietrichGebert/ponytail

Canonical: `https://github.com/DietrichGebert/ponytail` (MIT). Ruleset text read from
`AGENTS.md` and `skills/ponytail/SKILL.md` — this is the actual enforcement text.

### The ladder — stop at the first rung that holds

1. Does this need to exist at all? (YAGNI)
2. Already in this codebase? Reuse the helper/util/pattern.
3. Stdlib does it?
4. Native platform feature covers it? (`<input type="date">` over a picker lib; CSS over JS; DB constraint over app code)
5. Already-installed dependency solves it?
6. Can it be one line?
7. **Only then:** the minimum code that works.

**The ladder runs *after* understanding the problem, not instead of it.** Read the
code it touches and trace the real flow end to end *first*.
`Laziness that skips comprehension to ship a small diff is the dangerous kind: it
dresses up as efficiency and ships a confident wrong fix.`

### Actionable rules

- **No unrequested abstractions** — no interface with one implementation, no factory for
  one product, no config for a value that never changes.
- **No new dependency if avoidable.** No boilerplate nobody asked for.
- **Deletion over addition.** Fewest files possible. Shortest working diff wins.
- **Bug fix = root cause, not symptom.** Grep every caller of the function you're
  about to touch; one guard in the shared function beats a guard per caller.
  `patching only the path the ticket names leaves every sibling caller still broken.`
- **Edge-case-correct tiebreak**: two stdlib options of the same size → take the one
  correct on edge cases. Lazy means less code, not the flimsier algorithm.
- **Mark deliberate corner-cuts** with a `ponytail:` comment naming the ceiling and the
  upgrade path: `# ponytail: global lock, per-account locks if throughput matters`.
- **Never simplify away**: trust-boundary input validation, error handling that
  prevents data loss, security, accessibility basics, anything explicitly requested.
- **Hardware calibration is never "lazy"** — a real clock drifts, a sensor reads off.
  Leave the calibration knob.
- **Lazy code without its check is unfinished.** Non-trivial logic (branch, loop,
  parser, money/security path) leaves **ONE** runnable check: an assert-based
  `demo()`/`__main__` self-check or one small `test_*.py`. No frameworks, no fixtures.
  Trivial one-liners need no test.
- **Output discipline**: code first, then ≤3 short lines — what was skipped, when to
  add it. Pattern: `[code] → skipped: [X], add when [Y].`
- **Never stall on a defaultable question** — ship the lazy version and question it in
  the same response.
- **Intensities**: `lite` (build as asked, name the lazier alternative) / `full`
  (ladder enforced, default) / `ultra` (YAGNI extremist, challenge the requirement).
  Switch with `/ponytail lite|full|ultra|off`; default via `PONYTAIL_DEFAULT_MODE`
  env var or `~/.config/ponytail/config.json`. Level persists for the session.

### Install

Hermes (this stack): `hermes plugins install DietrichGebert/ponytail --enable`, then
restart Hermes. Registers skills as `ponytail:<skill>` and adds `/ponytail`,
`/ponytail-review`, `/ponytail-audit`, `/ponytail-debt`, `/ponytail-gain`, `/ponytail-help`.
Node must be on the **non-interactive** shell PATH or hooks error harmlessly.

Other hosts: Claude Code `/plugin marketplace add DietrichGebert/ponytail` then
`/plugin install ponytail@ponytail` (two separate prompts); Codex
`codex plugin marketplace add` + `codex plugin add`; Copilot CLI `copilot plugin
marketplace add` + `copilot plugin install`; Cursor
`git clone … && node ponytail/scripts/cursor-hooks.js install`; Gemini
`gemini extensions install <url>`; OpenCode 2 `{"plugins":["@dietrichgebert/ponytail"]}`.

### Honest benchmarking note (worth respecting)

The headline "~54% less code" is the **corrected** agentic figure: a headless Claude
Code session on tiangolo's `full-stack-fastapi-template`, 12 feature tickets, with/without
the skill, n=4, Haiku 4.5, scored on the resulting `git diff`. Results: ponytail
LOC −54%, tokens −22%, cost −20%, time −27%, **safety 100%**. The earlier flat
"80–94%" single-shot number was retracted as a conversational-baseline artifact
(issue #126). **The rule was never "fewest tokens"** — it's *write only what the task
needs, and never cut validation, error handling, security, or accessibility.* Code gets
small because it's necessary, not golfed. A bare "write one-liners" prompt drops a safety
guard to 95%; ponytail keeps every one.

---

## 6. microsoft/playwright

⚠️ **playwright.dev doc fetches were denied by the user mid-task and were not retried.**
Everything below is verified against the **locally installed `playwright@1.62.1`**
(`/usr/local/lib/node_modules/playwright/types/test.d.ts`) plus the local
`playwright-cli` skill — so it reflects the actual API surface of the installed version,
not a doc page. Canonical docs live at `https://playwright.dev/docs/test-configuration`
if you later want to re-verify.

Installed: `playwright@1.62.1`, `@playwright/cli@0.1.19`, `@playwright/mcp@0.0.82`.

### Multi-project × multi-viewport × visual comparison

```ts
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet',  width: 834,  height: 1112 },
  { name: 'mobile',  width: 390,  height: 844 },
];

export default defineConfig({
  testDir: './tests/e2e',

  // Key for visual comparison: segregate baselines per project AND per viewport.
  // Tokens: {snapshotDir} {testDir} {testFileDir} {testFileName} {testFilePath}
  //         {testName} {projectName} {arg} {ext}
  snapshotPathTemplate: '{testDir}/__screenshots__/{projectName}/{testFilePath}/{arg}{ext}',

  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  // Tolerant but not blind comparison.
  expect: {
    toHaveScreenshot: {
      threshold: 0.2,          // YIQ color-space tolerance; PW's own default
      maxDiffPixelRatio: 0.02, // alternative to maxDiffPixels (0-1)
      animations: 'disabled',  // PW default — freezes CSS animations
      caret: 'hide',           // PW default
      scale: 'css',            // PW default — stable vs deviceScaleFactor
    },
  },

  projects: VIEWPORTS.flatMap(vp => [
    { name: `chromium-${vp.name}`,
      use: { ...devices['Desktop Chrome'], viewport: { width: vp.width, height: vp.height } } },
    { name: `firefox-${vp.name}`,
      use: { ...devices['Desktop Firefox'], viewport: { width: vp.width, height: vp.height } } },
    { name: `webkit-${vp.name}`,
      use: { ...devices['Desktop Safari'],  viewport: { width: vp.width, height: vp.height } } },
  ]),
});
```

```ts
// In a test
await expect(page).toHaveScreenshot('dashboard.png', { fullPage: true });
// Update baselines after an INTENTIONALLY verified change:
//   npx playwright test --update-snapshots      (--update-snapshots replaces --update-snapshots-era)
```

Verified from the installed `test.d.ts`:

- `snapshotPathTemplate` resolves relative to `configDir`; `/` works as separator on all
  platforms; each token may be preceded by a single conditional character used **only if
  the token is non-empty** (so `{/projectName}` gracefully drops unnamed projects).
  Canonical example in the type defs:
  `'__screenshots__{/projectName}/{testFilePath}/{arg}{ext}'`.
- `toHaveScreenshot` defaults confirmed: `threshold` 0.2 (pixelmatch, YIQ),
  `animations: 'disabled'`, `caret: 'hide'`, `scale: 'css'`.
  `maxDiffPixels` and `maxDiffPixelRatio` are both **unset by default** — pick one.
- `snapshotSuffix` exists but is **discouraged** by the types in favour of
  `snapshotPathTemplate`.
- `TestProject` supports `name`, `use`, `testMatch`, `dependencies`, `teardown`.
  Pattern from the type defs: a `setup` project with `testMatch: /global.setup\.ts/`
  plus `teardown: 'teardown'`, with each browser project declaring
  `dependencies: ['setup']`. `--no-deps` skips them.
- `defineConfig({ projects: [{ name: 'Chromium', use: { browserName: 'chromium' } }] })`
  is the documented minimum; `use` at top level applies to all projects and project-level
  `use` overrides it.
- Run: `PLAYWRIGHT_HTML_OPEN=never npx playwright test` (suppresses the auto-opening
  HTML report — important for CI/agents). Debug: `npx playwright test --debug=cli`,
  then attach with `playwright-cli attach <session>`.
- `playwright-cli` gives browser-scraping/annotation power that generated TS does not:
  `open --browser=chrome|firefox|webkit`, `--mobile`, `--device="iPhone 15"`,
  `resize W H`, `snapshot --boxes`, `find --regex`, `console`, `requests`,
  `tracing-start/stop`, `show --annotate` (user draws boxes on the live page).

---

## Where the sources disagree

| Topic | OpenAI (vendor) | AceCloud / ParthSkills (third-party) | Resolution for this build |
|---|---|---|---|
| **Prompt verbosity** | Elaborate itineraries now *hurt*; delete them. | Offer a 22-prompt library and an 8-part framework. | **Vendor wins on substance.** Use structure, not volume. Keep Goal/Context/Constraints/Done; drop step-by-step procedure. Both third-party sources themselves concede "a longer prompt is not automatically better." |
| **Testing default** | Astra runs tests on its own — remove the instruction. | Add explicit *proportional* testing scopes and a close-out report. | **Both, reconciled.** Drop unconditional "always test"; keep a scoped rule + reporting format. This is not a contradiction, it's a change in default. |
| **Confirmation gates** | Astra is the most aligned model and won't act unsafely — *consider softening* boundaries that make it over-halt. | Install pre-authorization prompts and destructive-action gate lists. | **Genuine conflict.** Gate *irreversible/external/prod* actions explicitly. Leave routine reversible local work ungated. Softening is fine; removing gates for deploys/merges is not. |
| **Skill descriptions** | Keep them as short as possible; progressive disclosure. | Silent. | Follow OpenAI. |
| **Audit ownership** | Ask Astra to audit its own instructions. | AceCloud: `Do not modify the instruction files until I approve`. | **Both**: let the agent produce the audit, keep human sign-off on edits. |
| **Code volume** | Silent on minimalism. | Silent. | **Ponytail vs everything else.** Spec-kit expands artifacts; ponytail shrinks diffs. Compatible in sequence (spec decides *what*, ponytail constrains *how much*), but do not let spec-kit's artifact volume become implementation volume. |
| **Spec-kit phase style** | OpenAI says elaborate recipes over-constrain. | — | **Watch the tension.** spec-kit's `tasks.md` is elaborate by design. Resolve by treating the spec as a *contract* (what/acceptance criteria) and letting implementation stay minimal — never re-narrate the recipe to the agent at execution time. |

---

## Provenance

| Source | Status | How verified |
|---|---|---|
| OpenAI blog | reachable (HTTP 200) | full text |
| AceCloud | reachable (HTTP 200) | full text, 22 prompts extracted |
| ParthSkills | reachable (HTTP 200) | full text |
| spec-kit | reachable | README.md, `docs/installation.md`, `docs/install/one-time.md`, docs site `reference/overview.html` + `reference/agentic-sdd.html`, repo tree API, `src/specify_cli/integrations/hermes/` |
| ponytail | reachable | README.md, `AGENTS.md`, `skills/ponytail/SKILL.md` |
| **Playwright** | **playwright.dev DENIED by user — not retried** | installed `playwright@1.62.1` `types/test.d.ts` + local `playwright-cli` skill |