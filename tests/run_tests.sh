#!/usr/bin/env bash
# Run Homey Backup lint + tests — mirrors the CI workflow steps.
# Usage:
#   ./tests/run_tests.sh              # lint then run all tests
#   ./tests/run_tests.sh --cov        # lint + tests + coverage report
#   ./tests/run_tests.sh -v           # verbose pytest output
#   ./tests/run_tests.sh -k backup    # filter tests by name
#   ./tests/run_tests.sh --tb=short   # short tracebacks

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

cd "$REPO_DIR"

# Separate --cov from other pytest args
COV_ARGS=()
PYTEST_ARGS=()
for arg in "$@"; do
    if [[ "$arg" == "--cov" ]]; then
        COV_ARGS=("--cov" "--cov-report=html:tests/htmlcov" "--cov-report=term")
    else
        PYTEST_ARGS+=("$arg")
    fi
done

echo "Running lint (ruff check) ..."
uv run ruff check .

echo ""
echo "Running Homey Backup tests..."
echo "Directory: $REPO_DIR"
echo ""

uv run pytest tests/ "${COV_ARGS[@]}" "${PYTEST_ARGS[@]}"

if [[ ${#COV_ARGS[@]} -gt 0 ]]; then
    echo ""
    echo "Coverage report written to: tests/htmlcov/index.html"
fi
