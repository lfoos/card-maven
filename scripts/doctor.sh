#!/usr/bin/env bash
# Checks the tools Card Maven needs and says how to install anything missing.
# Used by `make doctor`, which `make bootstrap` runs first.
set -uo pipefail

failures=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✗\033[0m %s\n      → %s\n' "$1" "$2"; failures=$((failures + 1)); }

echo "Checking prerequisites…"

if ! command -v docker >/dev/null 2>&1; then
  fail "docker not found" "install OrbStack (brew install orbstack) or Docker Desktop, then open it once"
elif ! docker info >/dev/null 2>&1; then
  fail "docker is installed but not running" "start OrbStack / Docker Desktop (or: colima start)"
elif ! docker compose version >/dev/null 2>&1; then
  fail "docker compose v2 not available" "update Docker, or: brew install docker-compose"
else
  ok "docker $(docker version --format '{{.Server.Version}}' 2>/dev/null) with compose"
fi

if command -v uv >/dev/null 2>&1; then
  ok "$(uv --version)"
else
  fail "uv not found" "brew install uv   (then open a new terminal)"
fi

if command -v node >/dev/null 2>&1; then
  major=$(node --version | sed -E 's/^v([0-9]+).*/\1/')
  if [ "$major" -ge 22 ]; then ok "node $(node --version)"; else
    fail "node $(node --version) is too old (need 22+)" "brew install node@22 && brew link --overwrite node@22"
  fi
else
  fail "node not found" "brew install node@22"
fi

if command -v pnpm >/dev/null 2>&1; then
  ok "pnpm $(pnpm --version)"
else
  fail "pnpm not found" "brew install pnpm"
fi

if [ "$failures" -gt 0 ]; then
  printf '\n%d problem(s) found. Fix them, then rerun the command.\n' "$failures"
  exit 1
fi
echo "All set."
