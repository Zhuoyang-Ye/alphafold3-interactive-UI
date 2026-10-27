#!/bin/bash
# Convenience wrapper to run AlphaFold 3 inference on macOS (Apple Silicon).
# Uses the experimental JAX-MPS (Metal) backend, ~3x faster than CPU.
#
# Usage:  ./run_af3_macos.sh <input.json> [output_dir]
# Env:    MODEL_DIR (default ~/models), DB_DIR (default ~/public_databases)

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="/opt/homebrew/bin:${PATH}"

JSON_PATH="${1:?usage: ./run_af3_macos.sh <input.json> [output_dir]}"
OUTPUT_DIR="${2:-${REPO_DIR}/af_output}"
MODEL_DIR="${MODEL_DIR:-${HOME}/models}"
DB_DIR="${DB_DIR:-${HOME}/public_databases}"

cd "${REPO_DIR}"
uv run run_alphafold.py \
  --json_path="${JSON_PATH}" \
  --output_dir="${OUTPUT_DIR}" \
  --model_dir="${MODEL_DIR}" \
  --db_dir="${DB_DIR}" \
  --jax_backend=mps \
  --flash_attention_implementation=xla
