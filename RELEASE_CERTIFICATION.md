# ForkReason V1 — release certification

## Release certification — d5f4627

All gates green at this commit:

| Gate | Command | Result |
|---|---|---|
| Backend tests | `pytest apps/api/tests/` | **219 passed** |
| Backend lint | `pyflakes apps/api/forkreason/` | clean |
| Contract, Direct Mode | `gltest contracts/tests/ -m "not integration"` | **51 passed** |
| Contract, Studio Mode | `./deploy/studio/run-studio.sh` | **8 passed**, 5 validators |
| Contract lint | `genvm-lint contracts/forkreason_registry.py` | 3 checks |
| Frontend typecheck | `npm run typecheck` | clean |
| Frontend lint | `npm run lint` | clean |
| Frontend unit tests | `npm run test:unit` | **17 passed** |
| Frontend build | `npm run build` | 11 routes, bundle assets verified |
| Visual QA | `node scripts/capture.mjs` | 40 captures, 0 problems |

`main` is pushed to `https://github.com/0xbardia/ForkReason` at d5f4627.

### The published v1.0.0 tag does not point here

`v1.0.0` currently sits at `fcd6c47`, 14 commits behind. Moving it is a
force-push to an externally visible ref, so it is left for an explicit decision
rather than done silently. The work is on `main` either way.

### Known limitation, stated rather than hidden

`npm audit` reports 0 critical, 0 high, 22 moderate. Every moderate advisory is
the same transitive chain through `@rainbow-me/rainbowkit` →
`@walletconnect/utils` → `query-string`. `npm audit fix --force` would resolve
them by moving RainbowKit outside its supported peer range. See
`docs/SECURITY-FINDINGS.md` for why that is not applied.
