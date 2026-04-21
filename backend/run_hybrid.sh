#!/usr/bin/env bash
# Hybrid local stack: LiteLLM (in front of local vLLM + Ollama) + uvicorn backend.
#
# Prerequisites on the host:
#   - Python 3.11 venv at backend/.venv311 (or set VENV_DIR)
#   - vLLM already serving a chat model at $VLLM_BASE_URL (default :8000)
#   - Ollama already serving an embedding model at $EMBED_BASE_URL (default :11434)
#   - Redis running on REDIS_DB_HOST:REDIS_DB_PORT (optional, fail-open)
#
# Usage:
#   cd backend
#   bash run_hybrid.sh
#
# .env / .env.local are sourced automatically. Copy .env.hybrid.example into
# .env.local and fill in the non-default values (DEEPGRAM_API_KEY, maybe
# GOOGLE_APPLICATION_CREDENTIALS).

set -euo pipefail
cd "$(dirname "$0")"

VENV_DIR="${VENV_DIR:-.venv311}"
if [ ! -x "${VENV_DIR}/bin/python" ]; then
    VENV_DIR="../.venv"
fi
if [ ! -x "${VENV_DIR}/bin/python" ]; then
    echo "No usable venv found (.venv311 or ../.venv). Create one first:" >&2
    echo "  python3.11 -m venv .venv311 && source .venv311/bin/activate && pip install -r requirements.txt" >&2
    exit 1
fi
export PATH="$(cd "${VENV_DIR}/bin" && pwd):${PATH}"

set -a
source .env 2>/dev/null || true
source .env.local 2>/dev/null || true
set +a

# Hybrid-specific defaults (match .env.hybrid.example)
export VLLM_BASE_URL="${VLLM_BASE_URL:-http://localhost:8000/v1}"
export VLLM_MODEL_ID="${VLLM_MODEL_ID:-gemma-4-26b-a4b-it-fp8}"
export VLLM_API_KEY="${VLLM_API_KEY:-dummy}"
export EMBED_BASE_URL="${EMBED_BASE_URL:-http://localhost:11434}"
export EMBED_MODEL_ID="${EMBED_MODEL_ID:-nomic-embed-text}"
export LITELLM_MASTER_KEY="${LITELLM_MASTER_KEY:-sk-litellm-local-master}"
export LITELLM_PORT="${LITELLM_PORT:-4000}"

# Point Omi at LiteLLM instead of real OpenAI/Anthropic/OpenRouter
export OPENAI_API_KEY="${OPENAI_API_KEY:-${LITELLM_MASTER_KEY}}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://localhost:${LITELLM_PORT}/v1}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-${LITELLM_MASTER_KEY}}"
export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-http://localhost:${LITELLM_PORT}}"
export OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-${LITELLM_MASTER_KEY}}"

# Upstream health checks (fast-fail if vLLM / Ollama isn't reachable)
check_http() {
    local url="$1" label="$2"
    if ! curl -fsS --max-time 3 "${url}" >/dev/null 2>&1; then
        echo "[warn] ${label} not reachable at ${url}" >&2
        return 1
    fi
    return 0
}
check_http "${VLLM_BASE_URL%/v1}/v1/models" "vLLM" || echo "        (hybrid LLM routing will fail until vLLM is up)"
check_http "${EMBED_BASE_URL}/api/tags" "Ollama" || echo "        (embeddings will fail until Ollama is up)"

# Stash LiteLLM PID so we can shut it down cleanly
LITELLM_LOG="${LITELLM_LOG:-/tmp/litellm-hybrid.log}"
LITELLM_PID=""
cleanup() {
    if [ -n "${LITELLM_PID}" ] && kill -0 "${LITELLM_PID}" 2>/dev/null; then
        echo ""
        echo "[run_hybrid] stopping LiteLLM (pid ${LITELLM_PID})"
        kill "${LITELLM_PID}" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

if ! command -v litellm >/dev/null 2>&1; then
    echo "[run_hybrid] installing litellm[proxy] into ${VENV_DIR}"
    pip install --quiet 'litellm[proxy]'
fi

echo "[run_hybrid] starting LiteLLM on :${LITELLM_PORT} -> vLLM ${VLLM_MODEL_ID} + Ollama ${EMBED_MODEL_ID}"
litellm --config "$(pwd)/litellm_config.yaml" --port "${LITELLM_PORT}" \
    >"${LITELLM_LOG}" 2>&1 &
LITELLM_PID=$!

# Wait for LiteLLM to be reachable (up to ~15s)
for _ in $(seq 1 30); do
    if curl -fsS --max-time 1 "http://localhost:${LITELLM_PORT}/health/liveliness" >/dev/null 2>&1 \
        || curl -fsS --max-time 1 "http://localhost:${LITELLM_PORT}/v1/models" \
             -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

if ! kill -0 "${LITELLM_PID}" 2>/dev/null; then
    echo "[run_hybrid] LiteLLM died during startup. Last 40 lines of ${LITELLM_LOG}:" >&2
    tail -n 40 "${LITELLM_LOG}" >&2 || true
    exit 1
fi

echo "[run_hybrid] LiteLLM ready (pid ${LITELLM_PID}, log ${LITELLM_LOG})"
echo "[run_hybrid] starting backend via start_local.sh"
exec bash start_local.sh
