#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON="$PYTHON_BIN"
elif [[ -x "$HOME/.hermes/hermes-agent/venv/bin/python" ]]; then
  PYTHON="$HOME/.hermes/hermes-agent/venv/bin/python"
elif [[ -x "$HOME/.local/share/hermes-owner/home/.hermes/hermes-agent/venv/bin/python" ]]; then
  PYTHON="$HOME/.local/share/hermes-owner/home/.hermes/hermes-agent/venv/bin/python"
else
  PYTHON=python3
fi
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo 'Python unavailable; set PYTHON_BIN to an installed Python 3.' >&2
  exit 1
fi
exec "$PYTHON" "$ROOT/scripts/tunnel.py" "$@"
