# ForkReason — Build State

Living notes for this build. The durable source of truth for requirements is
`.specify/memory/constitution.md` and `specs/001-forkreason-v1/spec.md`.

## Verified environment

| Item | Value |
|---|---|
| Repo path | `/root/ForkReason` |
| Python | 3.12.13 via `uv`, venv at `.venv` |
| Node | 22.23.3 (`/root/.nvm/versions/node/v22.23.3/bin`) |
| PM2 | `/root/.nvm/versions/node/v20.20.2/bin/pm2`, systemd unit `pm2-root.service` |
| PostgreSQL | 18.6, db `forkreason`, user `forkreason`, password `forkreason_local_dev_2026` |
| Domain | `forkreason.bydx.fun` → 94.156.237.122 (DNS already correct) |
| TLS | certbot cert issued 2026-10-03, valid to 2027-01-01 |
| nginx | 1.28.3; per-site files in `/etc/nginx/sites-{available,enabled}` |
| GitHub | `gh` authenticated as `0xbardia` |
| GenLayer SDK | `genlayer-py@v0.18`, `genlayer-test@v0.29` (0.29.2), `genvm-linter` 0.11.1rc2 |
| Contract CLI | npm `genlayer` 0.40.0-rc.3 (needs Docker for Studio Mode) |
| GenLayer networks | `localnet`, `studionet`, `testnet_asimov`, `testnet_bradbury` |

## Ports

| Service | Port |
|---|---|
| ForkReason API | 8421 |
| ForkReason web | 3111 |
| Existing (do not disturb) | 3000, 3002, 3100, 4002, 4310, 4320, 4330, 8080, 8099, 8130, 4189, 18000 |

## Commands

```bash
# backend tests
PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/tests/ -q

# contract Direct Mode + injection suite
.venv/bin/gltest contracts/tests/ -v

# contract lint
.venv/bin/genvm-lint contracts/forkreason_registry.py

# migrations
DATABASE_URL=postgresql+psycopg://... .venv/bin/python -m alembic upgrade head
```

## Test counts (verified by real runs)

- Backend: **219 passing**
- Contract Direct Mode: **51 passing** (37 registry + 14 injection)
- `genvm-lint`: clean, 3 checks

## Fixture scenario verdicts (verified)

| Scenario | Verdict | Confidence |
|---|---|---|
| A derivation w/ rename+refactor | `LIKELY_DERIVED` | HIGH |
| B both derive from upstream | `SHARED_UPSTREAM` | HIGH |
| C independent same-spec | `INDEPENDENT` | MEDIUM |
| D insufficient history | `INSUFFICIENT_EVIDENCE` | LOW |
| F declared fork | `DECLARED_FORK` | HIGH |

## Product bugs found by tests (all fixed)

These were real defects, not test problems:

1. Structural similarity scored 1.000 for repos sharing only boilerplate.
   Fixed by filtering `COMMON_BOILERPLATE_TOKENS` before structural and shingle
   comparison.
2. "Target started after origin matured" scored 0.63 and alone could produce
   `LIKELY_DERIVED`. Capped at 0.35 and labelled permissive.
3. `POST_DERIVATION_DIVERGENCE` triggered on *low* similarity, so unrelated
   repos were reported as `HEAVILY_DERIVED`. Now requires relatedness plus a
   timeline that permits derivation.
4. `select_verdict` could emit a directional verdict when the target predates
   the origin. Now short-circuits.
5. Manifest hash depended on list order. Canonicalization now sorts
   order-insensitive collections.
6. `claim_job` cleared the lease in `finally`, permanently stranding crashed
   jobs. Lease now preserved on the failure path.
7. Starlette/FastAPI handler registration order broke the error envelope.
8. Evidence route default `limit=100` exceeded its own `le=50` bound.
9. `/api/v1/chain/status` router was never mounted.

## Gotchas discovered

- The PyPI package `genlayer` is a 0.0.1 placeholder. The real SDK comes from
  `git+https://github.com/genlayerlabs/genlayer-py@v0.18`.
- `urlsplit` strips ASCII tabs and newlines, so `"a\nb"` silently became
  `"ab"`. Repository input is now scanned for those characters *before* parsing.
- `TreeMap` does not auto-vivify on `__getitem__`; use `get_or_insert_default`.
- `DynArray` cannot be constructed in contract code.
- No on-chain timestamp exists; use `datetime.datetime.now()` (warped by
  `vm.warp`).
- `vm.mock_llm` matches first-registered-wins; call `clear_mocks()` to change
  the answer mid-test.

## Remaining work

- Studio Mode tests (needs `genlayer init`/`genlayer up` + Docker — check
  availability)
- Contract deployment to studio.genlayer.com
- Frontend (Next.js + design system + all surfaces)
- Playwright, visual QA loop
- Deployment to https://forkreason.bydx.fun
- Docs, GitHub publication, fresh-clone verification
- `FINAL_V1_REPORT.md`