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
#   ./tests/run_ci_local.sh               # run full matrix (3.11 + 3.12)
#   ./tests/run_ci_local.sh --python 3.11 # single version
#   ./tests/run_ci_local.sh -n            # dry-run (parse/validate only, no Docker pull)
#
# The first real run pulls the Docker image (~800 MB). Subsequent runs reuse the cache.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
WORKFLOW=".github/workflows/ci.yml"

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

if ! docker info &>/dev/null; then
  echo "Error: Docker is not running. Start Docker and try again."
  exit 1
fi

ACT_ARGS=(push --job lint-and-test $DRY_RUN)

if [[ -n "$PYTHON_VERSION" ]]; then
  ACT_ARGS+=(--matrix "python-version:${PYTHON_VERSION}")
fi

echo "Running CI workflow locally via act..."
echo "  Workflow : $WORKFLOW"
echo "  Args     : ${ACT_ARGS[*]}"
echo ""

act "${ACT_ARGS[@]}"
