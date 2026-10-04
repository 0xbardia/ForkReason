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

WEB_DIR="${1:-/root/ForkReason/apps/web}"
cd "$WEB_DIR"

echo "==> next build"
npx next build

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