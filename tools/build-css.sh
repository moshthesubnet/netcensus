#!/usr/bin/env bash
# Build frontend/styles.css from Tailwind sources.
#
# Replaces the cdn.tailwindcss.com script tag (which logs a production
# warning every page load and breaks air-gapped homelab use) with a
# minified static stylesheet, ~15 KB instead of ~360 KB.
#
# Re-run this script after editing frontend/index.html, frontend/styles.src.css,
# or frontend/tailwind.config.js. The first run downloads the standalone
# Tailwind CLI binary to tools/tailwindcss (gitignored).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

TAILWIND_VERSION="v3.4.17"
TAILWIND_BIN="tools/tailwindcss"

case "$(uname -m)" in
  x86_64|amd64)  ARCH="x64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  *) echo "Unsupported arch: $(uname -m)" >&2; exit 1 ;;
esac

case "$(uname -s)" in
  Linux)  PLATFORM="linux" ;;
  Darwin) PLATFORM="macos" ;;
  *) echo "Unsupported OS: $(uname -s)" >&2; exit 1 ;;
esac

if [ ! -x "$TAILWIND_BIN" ]; then
  echo "Downloading Tailwind CLI ${TAILWIND_VERSION} (${PLATFORM}-${ARCH})..."
  curl -sL \
    "https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/tailwindcss-${PLATFORM}-${ARCH}" \
    -o "$TAILWIND_BIN"
  chmod +x "$TAILWIND_BIN"
fi

"$TAILWIND_BIN" \
  -c frontend/tailwind.config.js \
  -i frontend/styles.src.css \
  -o frontend/styles.css \
  --minify

echo "Wrote frontend/styles.css ($(wc -c < frontend/styles.css) bytes)"
