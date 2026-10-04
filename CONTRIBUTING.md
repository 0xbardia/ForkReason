# Contributing to ForkReason

Thanks for considering it. ForkReason is a forensic tool, so the bar for a
change is that it makes the tool **more honest**, not merely more capable.

## The one rule that matters

**Do not make the tool agree more often.**

A change that raises the verdict rate without raising the evidence bar is a
regression, even if every test passes. If you tune scoring, include the fixture
scenario you tuned against so a reviewer can see the trade-off.

## Getting set up

```bash
git clone https://github.com/0xbardia/ForkReason.git
cd ForkReason
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env          # edit DATABASE_URL
.venv/bin/python -m alembic upgrade head

cd apps/web && npm ci
```

You need a PostgreSQL instance for the backend and integration tests.

## Before you open a pull request

```bash
# Backend — 205 tests
PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/tests/ -q

# Contract, Direct Mode — 51 tests, no network needed
.venv/bin/gltest contracts/tests/ -m "not integration" -q

# Contract lint
.venv/bin/genvm-lint contracts/forkreason_registry.py

# Frontend
cd apps/web && npx tsc --noEmit && npm run build
```

If you change the contract, Studio Mode must pass too:

```bash
./deploy/studio/run-studio.sh     # 8 tests, real 5-validator consensus
```

Then update [`contracts/RELEASE_CANDIDATE.md`](contracts/RELEASE_CANDIDATE.md):
a contract change invalidates the frozen source hash.

## Where things live

| Path | Contains |
|---|---|
| `apps/api/forkreason/analysis/` | The forensic engine: fingerprints, DNA, chronology, scoring |
| `apps/api/forkreason/repos/` | Safe intake: URL validation, `git archive` snapshots |
| `apps/api/forkreason/jobs/` | Durable queue, worker, recovery |
| `apps/api/forkreason/routes/` | Versioned API |
| `contracts/` | The GenLayer Intelligent Contract and its tests |
| `apps/web/` | Next.js frontend and design system |

## Adding a fixture scenario

This is the most useful contribution. Scenarios live in
`apps/api/tests/test_forensic_engine.py` and must be real repositories with real
history — not twenty-line toys, because a toy cannot exercise the chronology
rules that ForkReason actually depends on.

```python
def test_target_predates_origin(self):
    """B appears before A matured: derivation is impossible."""
    ...
```

State the expected verdict **and** why. If the honest answer is
`INSUFFICIENT_EVIDENCE`, say so — that is a valid and valuable expectation.

## Changing evidence scoring

1. Change the smallest thing that could work.
2. Run the full backend suite; all 205 tests must pass.
3. Add a fixture that fails without your change.
4. Explain in the PR what false positive or false negative you removed.

Prefer making a signal **weaker** over adding a threshold. A weight that says
"this counts less" is honest; a cutoff that hides the evidence is not.

## Style

- Python: type annotations, no `Any` where a real type exists, short functions.
- No new dependency without a reason in the PR body.
- Comments explain *why*, not *what*.
- Keep the evidence bounded. Do not widen limits to make a test pass.

## Reporting security issues

Not an issue — see [`SECURITY.md`](SECURITY.md) for private reporting.

## License

Contributions are licensed under AGPL-3.0, the same as the project.
