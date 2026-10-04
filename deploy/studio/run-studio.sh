#!/usr/bin/env bash
# Start a local Studio Mode environment and run the integration suite.
#
#   ./deploy/studio/run-studio.sh
#
# Components:
#   model_stub.py   OpenAI-compatible endpoint implementing ForkReason's
#                   decision schema. GLSim hardcodes api.openai.com and offers
#                   no base-URL override.
#   tls_proxy.py    CONNECT proxy mapping that hostname to the stub. Applied
#                   ONLY to the GLSim process via HTTPS_PROXY, so other services
#                   on this host (orbi_bot) keep using the real OpenAI.
#   glsim           5-validator network with leader rotation.
#
# `--leader-only` is never used: it would bypass the validator committee.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

STUB_PORT="${STUB_PORT:-8089}"
PROXY_PORT="${PROXY_PORT:-8443}"
CERT="$ROOT/deploy/studio/certs/cert.pem"

# A throwaway self-signed cert for api.openai.com, generated here rather than
# committed: a private key in the repository is a finding regardless of intent.
CERT_DIR="$ROOT/deploy/studio/certs"
mkdir -p "$CERT_DIR"

# Regenerated on EVERY run, not only when absent. An earlier version created it
# once and reused it, which meant a key written to disk in one run stayed the
# live interception key for every later run. It also means any copy of the key
# that escapes has a 1-day certificate, so it cannot be paired with a
# long-lived leaf to impersonate anything that trusts this host.
echo "==> generating throwaway TLS cert for api.openai.com"
rm -f "$CERT_DIR/cert.pem" "$CERT_DIR/key.pem"
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" \
  -days 1 -subj "/CN=api.openai.com" \
  -addext "subjectAltName=DNS:api.openai.com" 2>/dev/null
chmod 600 "$CERT_DIR/key.pem"

echo "==> model stub on 127.0.0.1:${STUB_PORT}"
.venv/bin/python deploy/studio/model_stub.py "$STUB_PORT" &
STUB_PID=$!

echo "==> CONNECT proxy on 127.0.0.1:${PROXY_PORT}"
.venv/bin/python deploy/studio/tls_proxy.py "$PROXY_PORT" "$STUB_PORT" &
PROXY_PID=$!

cleanup() {
  kill "$STUB_PID" "$PROXY_PID" "${GLSIM_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT

echo "==> waiting for the model stub"
for _ in $(seq 1 30); do
  if curl -s --max-time 2 -o /dev/null -X POST "http://127.0.0.1:${STUB_PORT}/v1/chat/completions" \
       -H 'Content-Type: application/json' \
       -d '{"messages":[{"role":"user","content":"ready"}]}'; then
    echo "    stub ready"
    break
  fi
  sleep 1
done

echo "==> glsim (5 validators, max 3 rotations)"
# Scoped to this process tree only.
export HTTPS_PROXY="http://127.0.0.1:${PROXY_PORT}"
export HTTP_PROXY="http://127.0.0.1:${PROXY_PORT}"
# GLSim's own JSON-RPC traffic to 127.0.0.1:4000 must NOT go through the
# intercept proxy, or the chain's own responses are answered by the model stub.
export NO_PROXY="127.0.0.1,localhost"
export no_proxy="127.0.0.1,localhost"
export REQUESTS_CA_BUNDLE="$CERT"
export SSL_CERT_FILE="$CERT"
# GLSim's LLM handler refuses to start without an OPENAI_API_KEY, even though
# every request is intercepted by the proxy above and the credential is never
# used. A clearly-fake placeholder satisfies that presence check.
export OPENAI_API_KEY="${OPENAI_API_KEY:-sk-forkreason-local-stub-not-a-real-key}"

.venv/bin/glsim \
  --port 4000 \
  --validators 5 \
  --max-rotations 3 \
  --llm-provider openai:gpt-4o-mini \
  --no-browser \
  --seed 42 &
GLSIM_PID=$!

# Wait for actual readiness rather than sleeping a fixed interval. A cold
# interpreter can take longer than 6s to load, and starting the suite early
# produces schema errors that look like contract failures.
echo "==> waiting for GLSim to accept requests"
for _ in $(seq 1 60); do
  if curl -s --max-time 2 -X POST http://127.0.0.1:4000/api \
       -H 'Content-Type: application/json' \
       -d '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' \
       | grep -q result; then
    echo "    GLSim ready"
    break
  fi
  sleep 1
done

echo "==> Studio Mode suite"
# gltest itself needs no proxy, but it inherits the env above harmlessly.
.venv/bin/gltest contracts/tests/ -m integration -v -s
