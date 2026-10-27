#!/bin/bash
# Save the running explorer as a read-only demo and publish it to the gh-pages
# branch, which GitHub Pages serves. Start the explorer first (run_explorer.sh).
#
# Usage: bash explorer/publish_demo.sh [explorer_url]   (default http://127.0.0.1:8765)

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_DIR}"
SERVER="${1:-http://127.0.0.1:8765}"
REPO_URL="$(gh repo view --json url -q .url 2>/dev/null || git remote get-url origin | sed -e 's/\.git$//')"
WORK="$(mktemp -d)"
SITE="${WORK}/site"
trap 'git worktree remove --force "${SITE}" > /dev/null 2>&1 || true; rm -rf "${WORK}"' EXIT

# Work in a temporary checkout so the current branch and files are untouched.
PARENT=""
if git fetch --quiet origin gh-pages 2> /dev/null; then
  PARENT="$(git rev-parse FETCH_HEAD)"
  git worktree add --quiet --detach "${SITE}" "${PARENT}"
else
  echo "Creating the gh-pages branch"
  git worktree add --quiet --detach "${SITE}"
  git -C "${SITE}" rm -r --quiet --cached .
fi
find "${SITE}" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +

.venv/bin/python -m explorer.build_demo --server "${SERVER}" --repo-url "${REPO_URL}" --out "${SITE}"

git -C "${SITE}" add --all
if [ -n "${PARENT}" ] && git -C "${SITE}" diff --cached --quiet "${PARENT}"; then
  echo "The published demo is already up to date."
  exit 0
fi
TREE="$(git -C "${SITE}" write-tree)"
COMMIT="$(git -C "${SITE}" commit-tree "${TREE}" ${PARENT:+-p "${PARENT}"} -m "Update explorer demo")"
git push --quiet origin "${COMMIT}:refs/heads/gh-pages"
echo "Published. GitHub Pages updates within a few minutes."
