#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
APP_DIR="${ROOT_DIR}/app"

BACKEND_PORT="${BACKEND_PORT:-8081}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
NGROK_DOMAIN="${NGROK_DOMAIN:-}"
NGROK_API_URL="http://127.0.0.1:4040/api/tunnels"
NGROK_LOG_FILE="/tmp/omi-ngrok-${BACKEND_PORT}.log"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_command curl
require_command ngrok
require_command python3

if ! curl -fsS "http://${BACKEND_HOST}:${BACKEND_PORT}/openapi.json" >/dev/null; then
  echo "Backend is not reachable at http://${BACKEND_HOST}:${BACKEND_PORT}" >&2
  echo "Start it first, for example:" >&2
  echo "  cd backend && BACKEND_HOST=0.0.0.0 BACKEND_PORT=${BACKEND_PORT} bash start_local.sh" >&2
  exit 1
fi

find_ngrok_url() {
  python3 - "$BACKEND_PORT" "$NGROK_API_URL" <<'PY'
import json
import sys
import urllib.request

port = sys.argv[1]
api_url = sys.argv[2]

try:
    with urllib.request.urlopen(api_url, timeout=2) as response:
        payload = json.load(response)
except Exception:
    sys.exit(1)

target = f":{port}"

for tunnel in payload.get("tunnels", []):
    public_url = tunnel.get("public_url", "")
    config = tunnel.get("config", {})
    addr = config.get("addr", "")
    if addr.endswith(target) and public_url.startswith("https://"):
        print(public_url)
        sys.exit(0)

sys.exit(1)
PY
}

if ! PUBLIC_URL="$(find_ngrok_url 2>/dev/null)"; then
  echo "Starting ngrok for port ${BACKEND_PORT}..."
  if [ -n "${NGROK_DOMAIN}" ]; then
    nohup ngrok http --domain="${NGROK_DOMAIN}" "${BACKEND_PORT}" >"${NGROK_LOG_FILE}" 2>&1 &
  else
    nohup ngrok http "${BACKEND_PORT}" >"${NGROK_LOG_FILE}" 2>&1 &
  fi

  for _ in $(seq 1 20); do
    sleep 1
    if PUBLIC_URL="$(find_ngrok_url 2>/dev/null)"; then
      break
    fi
  done
fi

if [ -z "${PUBLIC_URL:-}" ]; then
  echo "Failed to discover ngrok public URL. Check ${NGROK_LOG_FILE}" >&2
  exit 1
fi

cat > "${BACKEND_DIR}/.env.local" <<EOF
BASE_API_URL=${PUBLIC_URL}
BACKEND_HOST=0.0.0.0
BACKEND_PORT=${BACKEND_PORT}
LOCAL_DEVELOPMENT=true
EOF

cat > "${APP_DIR}/.dev.env" <<EOF
API_BASE_URL=${PUBLIC_URL}/
USE_WEB_AUTH=false
USE_AUTH_CUSTOM_TOKEN=true
EOF

echo "Prepared real-device local config."
echo "  Public URL:  ${PUBLIC_URL}"
echo "  Backend env: ${BACKEND_DIR}/.env.local"
echo "  App env:     ${APP_DIR}/.dev.env"
echo ""
echo "Next:"
echo "  1. Restart backend: cd backend && BACKEND_HOST=0.0.0.0 BACKEND_PORT=${BACKEND_PORT} bash start_local.sh"
echo "  2. Build app dev flavor from app/:"
echo "     API_BASE_URL=${PUBLIC_URL}/ USE_WEB_AUTH=false USE_AUTH_CUSTOM_TOKEN=true bash setup.sh ios"
echo "  3. Sign in on the dev app, pair the nRF52840 over BLE, then test transcription."
