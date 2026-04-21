# Local hybrid deployment (vLLM + Ollama + Tailscale)

Run the whole backend on an RTX-class workstation. LLM calls go to a local
vLLM, embeddings go to local Ollama, iPhones reach it over Tailscale.

## Topology

```
Seeed → iPhone  ──BLE──►  iPhone (Omi app)
                              │   (Tailscale)
                              ▼
               ┌──────── RTX 5090 workstation ────────┐
               │ uvicorn (main:app)  :8080 ← iPhone  │
               │    │                                │
               │    ├─► LiteLLM        :4000        │
               │    │     ├─► vLLM     :8000 (chat) │
               │    │     └─► Ollama  :11434 (embed)│
               │    │                                │
               │    ├─► Redis         :6379         │
               │    └─► Firestore (emulator or real)│
               └──────────────────────────────────────┘
```

## Prereqs on the workstation

- Python 3.11 (`deadsnakes` PPA on Ubuntu 24.04)
- `ffmpeg`, `libopus-dev`, `build-essential`
- Redis (`sudo apt install redis-server && sudo systemctl enable --now redis-server`)
- Tailscale (`curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up`)
- vLLM serving a chat model at `:8000` (already running as user `ten` in our
  setup: `gemma-4-26b-a4b-it-fp8`)
- Ollama serving an embedding model at `:11434` (`ollama pull nomic-embed-text`)

## First-time setup

```bash
git clone https://github.com/tsukuru-86/Comm0ns-omi.git
cd Comm0ns-omi/backend
python3.11 -m venv .venv311
source .venv311/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install 'litellm[proxy]'   # also auto-installed by run_hybrid.sh
```

## Config — only the hybrid-specific bits go in `.env.local`

`start_local.sh` already bakes in sensible defaults for `ADMIN_KEY`,
`ENCRYPTION_SECRET`, the Firestore emulator, and a throwaway service-account
key. The only thing you need to personalise is in `.env.local`:

```bash
cp .env.hybrid.example .env.local
# then edit .env.local and fill in at minimum:
#   DEEPGRAM_API_KEY=...            # Phase 1 STT (swap to local Whisper in Phase 2)
# optional:
#   GOOGLE_APPLICATION_CREDENTIALS=./google-credentials.json  # if you want a real Firebase project
#   FIREBASE_PROJECT_ID=<your-project>
```

The iPhone OAuth round-trip requires a **real** Firebase project, so once
you move past "backend talks to itself" testing:

1. Firebase Console → create project → Project settings → Service accounts →
   *Generate new private key*.
2. `scp` the downloaded JSON into `backend/google-credentials.json`.
3. In `.env.local`, set `GOOGLE_APPLICATION_CREDENTIALS=./google-credentials.json`,
   `FIREBASE_PROJECT_ID=<id>`, and `FIRESTORE_EMULATOR_HOST=` (empty to disable
   the emulator).

## Run

```bash
cd backend
bash run_hybrid.sh
```

That script:

1. Sources `.env` + `.env.local`.
2. Health-checks vLLM (`:8000`) and Ollama (`:11434`). Warns but doesn't abort
   if either is down — handy while you're still bringing services up.
3. Starts LiteLLM on `:4000` in the background (log: `/tmp/litellm-hybrid.log`).
4. Execs `start_local.sh`, which starts `uvicorn main:app --host 0.0.0.0 --port 8080`.

Ctrl-C stops both uvicorn and the LiteLLM child.

## Smoke tests

```bash
# Backend health
curl http://localhost:8080/health

# LiteLLM routing Gemma through the OpenAI schema
curl -s http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-litellm-local-master" \
  -H "Content-Type: application/json" \
  -d @- <<'EOF'
{"model":"gpt-4.1-mini","messages":[{"role":"user","content":"一行で自己紹介して"}]}
EOF

# Embeddings via Ollama
curl -s http://localhost:4000/v1/embeddings \
  -H "Authorization: Bearer sk-litellm-local-master" \
  -H "Content-Type: application/json" \
  -d '{"model":"text-embedding-3-large","input":"hello"}'
```

## iPhone side

The Flutter app obfuscates `API_BASE_URL` into a generated `.g.dart`, so
pointing the app at the workstation needs a rebuild:

1. Set `API_BASE_URL=http://<workstation-tailscale-ip>:8080` in `app/.dev.env`.
2. `cd app && bash setup.sh ios` (regenerates the envied `.g.dart`).
3. Build & install the dev flavor onto the iPhone via Xcode.

## Phase 2 — swap Deepgram for local Whisper

Once the hybrid stack above is running end-to-end, implement the Whisper
streaming server and point `STT_DEFAULT_REALTIME_PROVIDER=whisper_streaming`
(see `backend/utils/stt/providers/whisper.py` scaffold).
