#!/bin/bash
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${REPO_DIR}"
export PATH="/opt/homebrew/bin:${PATH}"
exec "${REPO_DIR}/.venv/bin/python" -m explorer.app "$@"
