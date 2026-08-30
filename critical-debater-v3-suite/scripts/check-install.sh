#!/usr/bin/env bash
# check-install.sh — verify the Critical Debater v3 installation
# 用法: bash scripts/check-install.sh [repo_root]
set -uo pipefail

REPO_ROOT="${1:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$REPO_ROOT" || exit 2

fail=0
say()  { printf '%s\n' "$*"; }
bad()  { printf 'FAIL: %s\n' "$*"; fail=1; }
good() { printf 'OK:   %s\n' "$*"; }

# 1. Python
if command -v python3 >/dev/null 2>&1; then
  PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
  good "python3 found ($PYV)"
else
  bad "python3 not found"; exit 2
fi

# 2. Package import + deps
if PYTHONPATH="$REPO_ROOT/src" python3 -c "import critical_debater" 2>/dev/null; then
  good "critical_debater package importable"
else
  bad "package not importable (run: pip install -e .)"; exit 2
fi
for dep in langgraph yaml fastapi uvicorn; do
  PYTHONPATH="$REPO_ROOT/src" python3 -c "import $dep" 2>/dev/null \
    && good "dependency: $dep" || bad "dependency missing: $dep"
done

# 3. Suite assets (capability docs + renderer)
if PYTHONPATH="$REPO_ROOT/src" python3 -c "
from critical_debater.paths import find_suite_dir, capability_path
d = find_suite_dir(); print(d)
capability_path('debate-turn.md')" 2>/dev/null; then
  SUITE_DIR=$(PYTHONPATH="$REPO_ROOT/src" python3 -c "
from critical_debater.paths import find_suite_dir; print(find_suite_dir())")
  good "skill suite discovered: $SUITE_DIR"
else
  bad "no skill suite found (set CRITICAL_DEBATER_SUITE_DIR)"; fail=1
fi

# 4. Runtime selection preview
RUNTIME=$(PYTHONPATH="$REPO_ROOT/src" python3 -c "
from critical_debater.models.registry import resolve_runtime; print(resolve_runtime())" 2>/dev/null || echo unknown)
case "$RUNTIME" in
  api) good "runtime: api (provider key detected)" ;;
  cli) good "runtime: cli (claude/codex CLI) — set a provider key for the API layer if desired" ;;
  *)   bad "runtime: none usable — export e.g. DEEPSEEK_API_KEY, or install claude/codex CLI" ;;
esac

# 5. Search backend
if [ -n "${TAVILY_API_KEY:-}" ] || [ -n "${BOCHA_API_KEY:-}" ]; then
  good "search backend key present"
else
  say "WARN: no search key (TAVILY_API_KEY / BOCHA_API_KEY) — source-ingest will fail the evidence gate honestly"
fi

# 6. Frontend build (optional)
if [ -f "$REPO_ROOT/frontend/dist/index.html" ]; then
  good "frontend built (frontend/dist)"
else
  say "WARN: frontend not built — Web UI unavailable (cd frontend && npm install && npm run build)"
fi

# 7. Tests runnable?
if PYTHONPATH="$REPO_ROOT/src" python3 -m pytest --version >/dev/null 2>&1; then
  good "pytest available"
else
  say "WARN: pytest not installed (pip install -e '.[dev]')"
fi

say ""
if [ "$fail" -eq 0 ]; then
  say "INSTALL CHECK PASSED / 安装校验通过"
  exit 0
fi
say "INSTALL CHECK FAILED / 安装校验未通过"
exit 1
