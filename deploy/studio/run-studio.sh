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
if [ ! -f "$CERT_DIR/cert.pem" ] || [ ! -f "$CERT_DIR/key.pem" ]; then
  echo "==> generating throwaway TLS cert for api.openai.com"
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" \
    -days 30 -subj "/CN=api.openai.com" \
    -addext "subjectAltName=DNS:api.openai.com" 2>/dev/null
  chmod 600 "$CERT_DIR/key.pem"
fi

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

sleep 2

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

sleep 6
echo "==> Studio Mode suite"
# gltest itself needs no proxy, but it inherits the env above harmlessly.
.venv/bin/gltest contracts/tests/ -m integration -v -s
