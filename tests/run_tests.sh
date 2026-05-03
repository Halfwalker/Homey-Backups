#!/usr/bin/env bash
# Run Homey Backup lint + tests — mirrors the CI workflow steps.
# Usage:
#   ./tests/run_tests.sh              # lint then run all tests
#   ./tests/run_tests.sh -v           # verbose pytest output
#   ./tests/run_tests.sh -k backup    # filter tests by name
#   ./tests/run_tests.sh --tb=short   # short tracebacks

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

cd "$REPO_DIR"

echo "Running lint (ruff check) ..."
uv run ruff check .

echo ""
echo "Running Homey Backup tests..."
echo "Directory: $REPO_DIR"
echo ""

uv run pytest tests/ "$@"
