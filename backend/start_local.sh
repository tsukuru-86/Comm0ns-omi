#!/usr/bin/env bash
# Start the full backend locally with dummy credentials for services we don't need.
# Real STT works via DEEPGRAM_API_KEY in .env.
#
# Usage:
#   cd backend
#   bash start_local.sh

set -euo pipefail
cd "$(dirname "$0")"

VENV_DIR="${VENV_DIR:-.venv311}"

if [ ! -x "${VENV_DIR}/bin/python" ]; then
    echo "Missing ${VENV_DIR}. Create it with: python3.11 -m venv ${VENV_DIR}" >&2
    exit 1
fi

export PATH="$(pwd)/${VENV_DIR}/bin:${PATH}"

# Load real keys from .env
set -a
source .env 2>/dev/null || true
source .env.local 2>/dev/null || true
set +a

# Generate dummy service account if not set
if [ -z "${SERVICE_ACCOUNT_JSON:-}" ]; then
    export SERVICE_ACCOUNT_JSON="$(
        python - <<'PY'
import json
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
pem = key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()

print(
    json.dumps(
        {
            'type': 'service_account',
            'project_id': 'demo-project',
            'private_key_id': 'k1',
            'private_key': pem,
            'client_email': 'demo@demo.iam.gserviceaccount.com',
            'client_id': '1',
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
        }
    )
)
PY
    )"
fi

if [ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]; then
    export GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/google-credentials.json"
elif [[ "${GOOGLE_APPLICATION_CREDENTIALS}" != /* ]]; then
    export GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/${GOOGLE_APPLICATION_CREDENTIALS}"
fi

export FIREBASE_PROJECT_ID="${FIREBASE_PROJECT_ID:-demo-project}"
export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-${FIREBASE_PROJECT_ID}}"
export GCLOUD_PROJECT="${GCLOUD_PROJECT:-${GOOGLE_CLOUD_PROJECT}}"

# Point Firestore/Storage to emulator (no real GCP needed)
export FIRESTORE_EMULATOR_HOST="${FIRESTORE_EMULATOR_HOST:-localhost:8080}"
export STORAGE_EMULATOR_HOST="${STORAGE_EMULATOR_HOST:-localhost:9199}"

# Required env vars with safe defaults
export ADMIN_KEY="${ADMIN_KEY:-local-dev-admin}"
export LOCAL_DEVELOPMENT="${LOCAL_DEVELOPMENT:-true}"
export ENCRYPTION_SECRET="${ENCRYPTION_SECRET:-omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-sk-dummy-key-for-local-dev}"
export TYPESENSE_API_KEY="${TYPESENSE_API_KEY:-dummy-typesense-key}"
export TYPESENSE_HOST="${TYPESENSE_HOST:-localhost}"

# STT defaults
export STT_DEFAULT_REALTIME_PROVIDER="${STT_DEFAULT_REALTIME_PROVIDER:-deepgram_streaming}"
export STT_DEFAULT_FINALIZE_PROVIDER="${STT_DEFAULT_FINALIZE_PROVIDER:-deepgram_batch}"
export BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
export BACKEND_PORT="${BACKEND_PORT:-8080}"

echo "=== Local Backend Startup ==="
echo "  Python:    $(python --version)"
echo "  Deepgram:  ${DEEPGRAM_API_KEY:+set (len=${#DEEPGRAM_API_KEY})}"
echo "  Venv:      ${VENV_DIR}"
echo "  Project:   ${GOOGLE_CLOUD_PROJECT}"
echo "  Firestore: ${FIRESTORE_EMULATOR_HOST} (emulator)"
echo "  Listen:    ${BACKEND_HOST}:${BACKEND_PORT}"
echo "  Admin key: ${ADMIN_KEY}"
echo "  Local dev: ${LOCAL_DEVELOPMENT}"
echo ""

exec python -m uvicorn main:app --host "${BACKEND_HOST}" --port "${BACKEND_PORT}" --log-level info
