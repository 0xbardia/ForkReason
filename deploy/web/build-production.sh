#!/usr/bin/env bash
# Build the frontend for production and produce a runnable standalone bundle.
#
# `output: "standalone"` emits the server and the node_modules it traced, but it
# deliberately does NOT copy `.next/static` or `public/` into that directory.
# Next expects the operator to place them. assemble-standalone.sh does that.
#
# This script exists because that two-step requirement is a trap: running a
# plain `next build` afterwards deletes the copies and the deployed site keeps
# serving HTML while every CSS and JS request 400s. The failure is silent --
# pages return 200, only the assets fail -- so it was live before it was found.
# Building through this script is the only supported path to a deployable
# bundle, and it always leaves the bundle assembled.
set -euo pipefail

# Default to the checkout this script lives in, not a fixed path, so the
# build works from any clone.
WEB_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/apps/web}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$WEB_DIR"

echo "==> next build"
# Next loads .env files from apps/web, while ForkReason keeps the deployment
# environment at the repository root. Forward only browser-safe values so a
# build from a fresh clone gets the same chain/API configuration as PM2.
node - "$ROOT_DIR" <<'NODE'
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { loadEnvConfig } = require("@next/env");

const env = { ...process.env };
loadEnvConfig(path.resolve(process.argv[2]), false);
for (const key of [
  "NEXT_PUBLIC_APP_URL",
  "NEXT_PUBLIC_API_URL",
  "NEXT_PUBLIC_GENLAYER_NETWORK",
  "NEXT_PUBLIC_GENLAYER_RPC_URL",
  "NEXT_PUBLIC_GENLAYER_CONTRACT_ADDRESS",
  "NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID",
]) {
  if (env[key] === undefined && process.env[key] !== undefined) env[key] = process.env[key];
}
const result = spawnSync("npx", ["next", "build"], { stdio: "inherit", env });
if (result.error) throw result.error;
process.exit(result.status ?? 1);
NODE

echo "==> assembling standalone bundle"
bash "$(dirname "$0")/assemble-standalone.sh" "$WEB_DIR"

# Prove the assets are actually where the server will look for them. Without
# this check a partial copy ships silently.
STANDALONE="$WEB_DIR/.next/standalone/apps/web"
missing=0
for required in ".next/static" "server.js"; do
  if [ ! -e "$STANDALONE/$required" ]; then
    echo "error: $STANDALONE/$required is missing; the bundle is not deployable" >&2
    missing=1
  fi
done
if [ "$missing" -ne 0 ]; then
  exit 1
fi

chunks=$(find "$STANDALONE/.next/static" -name '*.js' | wc -l)
styles=$(find "$STANDALONE/.next/static" -name '*.css' | wc -l)
echo "==> verified: $chunks JS chunk(s), $styles stylesheet(s) in the bundle"
