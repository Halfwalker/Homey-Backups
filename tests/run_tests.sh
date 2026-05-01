#!/usr/bin/env bash
# Run Homey Backup tests
# Usage:
#   ./tests/run_tests.sh              # run all tests
#   ./tests/run_tests.sh -v           # verbose
#   ./tests/run_tests.sh -k backup    # filter by name
#   ./tests/run_tests.sh --tb=short   # short tracebacks

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

cd "$REPO_DIR"

echo "Running Homey Backup tests..."
echo "Directory: $REPO_DIR"
echo ""

uv run pytest tests/ "$@"
