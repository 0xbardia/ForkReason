# Deployment

ForkReason runs at **https://forkreason.bydx.fun**.

## Shape

```
nginx (TLS, security headers)
  │
  ├── /                 → 127.0.0.1:3112   forkreason-web   (Next.js)
  ├── /_next/static/    → cached immutably
  ├── /api/             → 127.0.0.1:8421   forkreason-api   (FastAPI)
  ├── /health           → 127.0.0.1:8421
  └── /ready            → 127.0.0.1:8421

forkreason-worker — no listener, claims jobs from PostgreSQL
PostgreSQL       — 127.0.0.1:5432, not publicly reachable
```

Nothing but nginx is exposed. The API, worker and database are loopback-only.

## Processes

`ecosystem.config.cjs` defines three PM2 applications. It is a `.cjs` file
because a `/root/package.json` with `"type": "module"` otherwise forces ESM.

```bash
pm2 start ecosystem.config.cjs
pm2 save
pm2 startup          # once, to survive reboot
```

### A trap worth knowing

**PM2's daemon inherits whatever environment started it.** During development the
Studio Mode harness exported `HTTPS_PROXY` to redirect GLSim's model calls; PM2
picked it up, and every production GitHub request was refused with
`github_unreachable`. The ecosystem config now scrubs proxy and key variables
explicitly:

```js
const SCRUBBED = {};
for (const key of ["HTTP_PROXY", "HTTPS_PROXY", "REQUESTS_CA_BUNDLE",
                   "SSL_CERT_FILE", "OPENAI_API_KEY", /* … */]) {
  SCRUBBED[key] = "";
}
```

If GitHub validation starts failing in production, check the process environment
before anything else.

## nginx

```bash
install -m 644 deploy/nginx/forkreason.bydx.fun.conf \
  /etc/nginx/sites-available/forkreason.bydx.fun
nginx -t && systemctl reload nginx
```

Key decisions:

- **CSP is set by the Next middleware, not nginx.** Two policies intersect, and
  a nonce in one does not satisfy the other. nginx sets the *other* security
  headers only.
- **HTML is `no-store`.** The CSP nonce is per request, so cached HTML would
  carry a stale nonce and break hydration.
- **`/_next/static/` is immutable for a year.** Those filenames are content
  hashes.
- **`proxy_read_timeout` is 30 s.** Analysis is queued, never inline, so no
  legitimate request takes minutes. A longer timeout would only mask a stuck
  worker.
- **`client_max_body_size 1m`.** A submission carries a bounded evidence digest,
  not a repository.

## Environment

`.env` is gitignored. Production values:

| Variable | Value |
|---|---|
| `APP_ENV` | `production` |
| `APP_URL` | `https://forkreason.bydx.fun` |
| `CORS_ORIGINS` | `https://forkreason.bydx.fun` |
| `NEXT_PUBLIC_API_URL` | *(empty — same-origin through nginx)* |

`NEXT_PUBLIC_*` values are inlined into the client bundle **at build time**.
Rebuild the frontend after changing them:

```bash
cd apps/web && npm run build && pm2 restart forkreason-web --update-env
```

## Release procedure

```bash
# 1. Full suite
PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/tests/ -q
.venv/bin/gltest contracts/tests/ -m "not integration" -q
./deploy/studio/run-studio.sh
cd apps/web && npx tsc --noEmit && npm run build && cd ../..

# 2. Deploy
pm2 restart ecosystem.config.cjs --update-env

# 3. Verify
curl -sI http://forkreason.bydx.fun/docs          # 301 → https
curl -s  https://forkreason.bydx.fun/health
curl -s  https://forkreason.bydx.fun/ready
```

## Verification checklist

- [ ] `http://` returns `301` to `https://`
- [ ] `/`, `/trace`, `/explore`, `/docs`, `/docs/<section>`, `/security` → 200
- [ ] `/case/<id>`, `/case/<id>/evidence`, `/case/<id>/challenge` → 200
- [ ] `/health` and `/ready` → 200
- [ ] `/api/v1/cases` returns real data
- [ ] HSTS, `nosniff`, `X-Frame-Options: DENY` present
- [ ] CSP carries a nonce, and no `localhost` appears in it
- [ ] PostgreSQL not reachable from outside the host
