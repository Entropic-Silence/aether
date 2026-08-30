#!/usr/bin/env bash
# Reconnect large model files kept on a persistent volume.
# Safe and idempotent: never replaces an existing file or directory.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PERSISTED_MODELS="${AETHER_PERSISTED_MODELS_DIR:-/var/lib/aether/models}"
MODEL_LINK="$ROOT/data/models"

mkdir -p "$ROOT/data"
if [ -d "$PERSISTED_MODELS" ] && [ ! -e "$MODEL_LINK" ] && [ ! -L "$MODEL_LINK" ]; then
  ln -s "$PERSISTED_MODELS" "$MODEL_LINK"
fi

if [ -L "$MODEL_LINK" ] && [ ! -d "$MODEL_LINK" ]; then
  echo "[restore] model link is broken: $MODEL_LINK -> $(readlink "$MODEL_LINK")" >&2
  exit 1
fi
