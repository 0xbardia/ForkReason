#!/usr/bin/env bash
# Assemble the standalone Next bundle into a runnable server directory.
#
# `output: "standalone"` emits a minimal server plus the node_modules it traced,
# but it deliberately does NOT copy `.next/static` or `public/` into that
# directory — Next expects the operator to place them alongside. Without this
# step the server starts and returns correct HTML, but the browser can load no
# JavaScript, so React never hydrates and every client-rendered surface stays a
# skeleton forever. That presented as case pages rendering nothing while the API
# returned 200 for the same case.
#
# The trace root is the monorepo, so the bundle nests under apps/web.
set -euo pipefail

WEB_DIR="${1:-/root/ForkReason/apps/web}"
STANDALONE="$WEB_DIR/.next/standalone/apps/web"

if [ ! -f "$STANDALONE/server.js" ]; then
  echo "error: $STANDALONE/server.js not found. Run 'next build' first." >&2
  exit 1
fi

# Static assets are read from .next/static next to the server.
mkdir -p "$STANDALONE/.next"
rm -rf "$STANDALONE/.next/static"
cp -r "$WEB_DIR/.next/static" "$STANDALONE/.next/static"

# Public files are served from ./public next to the server.
if [ -d "$WEB_DIR/public" ]; then
  rm -rf "$STANDALONE/public"
  cp -r "$WEB_DIR/public" "$STANDALONE/public"
fi

echo "standalone bundle assembled at $STANDALONE"