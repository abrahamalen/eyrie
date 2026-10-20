#!/usr/bin/env bash
# Record the user-journey suite (frontend/e2e) against a throwaway Eyrie and build the report.
#
# Everything runs in a mktemp dir: HOME, ~/.eyrie, the tools' state, stand-in claude/codex
# binaries and a private tmux server (-L eyrie-e2e, own TMUX_TMPDIR). The real ~/.eyrie,
# ~/.claude, ~/.codex and your own tmux are never touched. Extra args go to Playwright,
# e.g. scripts/journeys.sh -g "Tasks" --project desktop.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${JOURNEY_BACKEND_PORT:-18765}"
FRONTEND_PORT="${JOURNEY_FRONTEND_PORT:-15199}"
SOCKET="eyrie-e2e"
OUT="$REPO/frontend/journeys"

ROOT="$(mktemp -d "${TMPDIR:-/tmp}/eyrie-journeys.XXXXXX")"
# The real path (macOS /var is /private/var), so paths the backend reports match the spec's.
ROOT="$(cd "$ROOT" && pwd -P)"
pids=()
cleanup() {
  local pid
  for pid in "${pids[@]}"; do
    pkill -P "$pid" 2>/dev/null || true
    kill "$pid" 2>/dev/null || true
  done
  if [[ -n "${TMUX_BIN:-}" ]]; then
    TMUX_TMPDIR="$ROOT/tmux" "$TMUX_BIN" -L "$SOCKET" kill-server 2>/dev/null || true
  fi
  rm -rf "$ROOT"
}
trap cleanup EXIT INT TERM

TMUX_BIN="$(command -v tmux || true)"
[[ -n "$TMUX_BIN" ]] || { echo "tmux isn't installed; the sessions journeys need it" >&2; exit 1; }

"$REPO/backend/.venv/bin/python" "$REPO/frontend/e2e/env/seed.py" "$ROOT"
mkdir -p "$ROOT/tmux"
# tmux refuses a socket dir others can read.
chmod 700 "$ROOT/tmux"

# PATH is minimal on purpose: the real claude / codex / gemini must not be found.
env -i \
  HOME="$ROOT/home" \
  PATH="$ROOT/bin:/usr/bin:/bin" \
  LANG="${LANG:-en_US.UTF-8}" \
  TMUX_TMPDIR="$ROOT/tmux" \
  EYRIE_CONFIG="$ROOT/home/.eyrie/eyrie.toml" \
  EYRIE_CLI__CLAUDE_BIN="$ROOT/bin/claude" \
  EYRIE_CLI__CODEX_BIN="$ROOT/bin/codex" \
  EYRIE_CLI__TMUX_BIN="$TMUX_BIN" \
  EYRIE_SESSIONS__SOCKET="$SOCKET" \
  "$REPO/backend/.venv/bin/python" "$REPO/frontend/e2e/env/serve.py" "$BACKEND_PORT" \
  >"$ROOT/backend.log" 2>&1 &
pids+=("$!")

(cd "$REPO/frontend" && EYRIE_BACKEND_PORT="$BACKEND_PORT" \
  exec npx vite --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort) >"$ROOT/frontend.log" 2>&1 &
pids+=("$!")

wait_for() {
  local url="$1" i
  for i in $(seq 1 60); do
    curl -sf -o /dev/null "$url" && return 0
    sleep 0.5
  done
  echo "Timed out waiting for $url" >&2
  cat "$ROOT/backend.log" "$ROOT/frontend.log" >&2
  return 1
}
wait_for "http://127.0.0.1:$BACKEND_PORT/api/v1/health"
wait_for "http://127.0.0.1:$FRONTEND_PORT/"

rm -rf "$OUT/raw"
status=0
(cd "$REPO/frontend" && \
  PLAYWRIGHT_BASE_URL="http://localhost:$FRONTEND_PORT" \
  JOURNEY_ROOT="$ROOT" \
  JOURNEY_TMUX="$TMUX_BIN" \
  JOURNEY_SOCKET="$SOCKET" \
  npx playwright test -c playwright.journeys.config.ts "$@") || status=$?

cp "$REPO/frontend/e2e/descriptions.json" "$OUT/descriptions.json"
python3 "$REPO/scripts/journey_report.py" "$OUT"
echo "Report: $OUT/index.html"
exit "$status"
