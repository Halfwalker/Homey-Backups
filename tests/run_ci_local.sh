#!/usr/bin/env bash
# Run the GitHub Actions CI workflow locally using nektos/act.
#
# Requirements:
#   - Docker running
#   - act installed: https://github.com/nektos/act
#     macOS:  brew install act
#     Linux:  curl --proto '=https' --tlsv1.2 -sSf https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash
#
# Usage:
#   ./tests/run_ci_local.sh               # run full matrix (3.11 then 3.12) sequentially
#   ./tests/run_ci_local.sh --python 3.11 # single version
#   ./tests/run_ci_local.sh -n            # dry-run (parse/validate only, no Docker pull)
#
# The first real run pulls the Docker image (~800 MB). Subsequent runs reuse the cache.
# Note: act runs matrix versions sequentially to keep output readable. GitHub/Gitea
#       runs them in parallel — this is intentional.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
WORKFLOW=".github/workflows/ci.yml"
MATRIX_VERSIONS=("3.11" "3.12")

# Parse optional flags
DRY_RUN=""
PYTHON_VERSION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--dry-run)
      DRY_RUN="-n"
      shift
      ;;
    --python)
      PYTHON_VERSION="$2"
      shift 2
      ;;
    *)
      echo "Unknown flag: $1"
      echo "Usage: $0 [--python VERSION] [-n]"
      exit 1
      ;;
  esac
done

cd "$REPO_DIR"

if [[ ! -f "$WORKFLOW" ]]; then
  echo "Error: $WORKFLOW not found. Run from the repo root or check the path."
  exit 1
fi

if ! command -v act &>/dev/null; then
  echo "Error: 'act' is not installed."
  echo "  macOS:  brew install act"
  echo "  Linux:  curl --proto '=https' --tlsv1.2 -sSf https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash"
  exit 1
fi

if [[ -z "$DRY_RUN" ]] && ! docker info &>/dev/null; then
  echo "Error: Docker is not running. Start Docker and try again."
  exit 1
fi

run_for_version() {
  local version="$1"
  local label="  Python ${version}"
  local inner=57  # dashes between ┌ and ┐
  local pad; pad=$(printf '%*s' $(( inner - ${#label} )) '')
  echo ""
  echo "┌─────────────────────────────────────────────────────────┐"
  echo "│${label}${pad}│"
  echo "└─────────────────────────────────────────────────────────┘"
  act push --job lint-and-test --matrix "python-version:${version}" $DRY_RUN
}

OVERALL=0

if [[ -n "$PYTHON_VERSION" ]]; then
  run_for_version "$PYTHON_VERSION" || OVERALL=1
else
  for v in "${MATRIX_VERSIONS[@]}"; do
    run_for_version "$v" || OVERALL=1
  done
fi

echo ""
if [[ $OVERALL -eq 0 ]]; then
  echo "✅  All matrix versions passed."
else
  echo "❌  One or more matrix versions failed."
fi
exit $OVERALL
