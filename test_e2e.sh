#!/usr/bin/env bash
#
# End-to-end test: starts both agents, sends an eval request, checks results.
# Run from the monorepo root on a machine with Docker installed.
#
# Usage:
#   ./test_e2e.sh                          # Real mode with default model (Sonnet 4.5)
#   ./test_e2e.sh --gold                   # Gold mode: known-correct patch (fast pipeline test)
#   ./test_e2e.sh --model gpt-4o-mini      # Real mode with a specific model
#   ./test_e2e.sh --model gpt-4o-mini --gold  # Gold mode (--model ignored)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
GREEN_DIR="$REPO_ROOT/packages/green-agent"
PURPLE_DIR="$REPO_ROOT/packages/purple-agent"

GREEN_PORT=9011
PURPLE_PORT=9012

GREEN_PID=""
PURPLE_PID=""

# Parse args
PURPLE_EXTRA_ARGS=""
MODE="real (mini-swe-agent)"
MODEL=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --gold)
            PURPLE_EXTRA_ARGS="$PURPLE_EXTRA_ARGS --use-gold-patches"
            MODE="gold patches (pipeline test)"
            shift ;;
        --model)
            MODEL="$2"
            PURPLE_EXTRA_ARGS="$PURPLE_EXTRA_ARGS --model $2"
            shift 2 ;;
        *)
            echo "Unknown arg: $1"; exit 1 ;;
    esac
done
if [[ -n "$MODEL" && "$MODE" != *"gold"* ]]; then
    MODE="real (mini-swe-agent, model: $MODEL)"
fi

cleanup() {
    echo ""
    echo "==> Cleaning up..."
    [[ -n "$GREEN_PID" ]] && kill "$GREEN_PID" 2>/dev/null || true
    [[ -n "$PURPLE_PID" ]] && kill "$PURPLE_PID" 2>/dev/null || true
    wait 2>/dev/null || true
    echo "==> Done."
}
trap cleanup EXIT

echo "==> Mode: $MODE"
echo ""

# --- 1. Start purple agent (participant) ---
echo "==> Starting purple agent on :${PURPLE_PORT}..."
cd "$PURPLE_DIR"
uv run python src/server.py --host 127.0.0.1 --port "$PURPLE_PORT" --data-dir data $PURPLE_EXTRA_ARGS &
PURPLE_PID=$!

# --- 2. Start green agent (evaluator) ---
echo "==> Starting green agent on :${GREEN_PORT}..."
cd "$GREEN_DIR"
uv run python src/server.py --host 127.0.0.1 --port "$GREEN_PORT" --data-dir data &
GREEN_PID=$!

# --- 3. Wait for both agents to be ready ---
echo "==> Waiting for agents to start..."
for port in "$PURPLE_PORT" "$GREEN_PORT"; do
    for i in $(seq 1 30); do
        if curl -sf "http://127.0.0.1:${port}/.well-known/agent-card.json" > /dev/null 2>&1; then
            echo "    Agent on :${port} is ready."
            break
        fi
        if [ "$i" -eq 30 ]; then
            echo "ERROR: Agent on :${port} did not start in time."
            exit 1
        fi
        sleep 0.5
    done
done

# --- 4. Send eval request to green agent ---
echo ""
echo "==> Sending evaluation request to green agent..."
echo "    (This will: green→purple for patch, then green runs Docker eval)"
echo ""

cd "$REPO_ROOT"
uv run python test_e2e_client.py \
    --green-url "http://127.0.0.1:${GREEN_PORT}" \
    --purple-url "http://127.0.0.1:${PURPLE_PORT}"

echo ""
echo "==> E2E test complete!"
