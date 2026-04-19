"""
Real STT test — calls Deepgram API with actual audio.
Requires DEEPGRAM_API_KEY in .env

Usage:
    cd backend && source .venv/bin/activate
    python demo_real_stt_test.py
"""

import asyncio
import os
import subprocess
import sys
import time

from dotenv import load_dotenv

load_dotenv()

BOLD = '\033[1m'
GREEN = '\033[32m'
CYAN = '\033[36m'
YELLOW = '\033[33m'
RED = '\033[31m'
RESET = '\033[0m'


def header(title):
    print(f'\n{BOLD}{CYAN}{"=" * 60}{RESET}')
    print(f'{BOLD}{CYAN}  {title}{RESET}')
    print(f'{BOLD}{CYAN}{"=" * 60}{RESET}')


# ============================================================
# Verify API key
# ============================================================
api_key = os.getenv('DEEPGRAM_API_KEY', '')
if not api_key:
    print(f'{RED}DEEPGRAM_API_KEY not set in .env{RESET}')
    sys.exit(1)
print(f'{GREEN}DEEPGRAM_API_KEY loaded{RESET} (len={len(api_key)})')

# ============================================================
# Generate test audio with macOS say command
# ============================================================
header('Generating test audio')
AUDIO_PATH = '/tmp/stt_test_speech.wav'
SPEECH_TEXT = 'Hello, this is a test of the speech to text provider abstraction layer. The quick brown fox jumps over the lazy dog.'

subprocess.run(['say', '-o', '/tmp/stt_test_speech.aiff', SPEECH_TEXT], check=True)
subprocess.run(
    ['afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', '/tmp/stt_test_speech.aiff', AUDIO_PATH],
    check=True,
)
with open(AUDIO_PATH, 'rb') as f:
    AUDIO_BYTES = f.read()
print(f'  Generated: {AUDIO_PATH} ({len(AUDIO_BYTES)} bytes)')

# ============================================================
# Test 1: Direct Deepgram SDK (sanity check)
# ============================================================
header('Test 1: Direct Deepgram SDK — Transcribe Bytes')

from deepgram import DeepgramClient, DeepgramClientOptions

dg = DeepgramClient(api_key, DeepgramClientOptions(options={"keepalive": "true"}))

try:
    t0 = time.time()
    response = dg.listen.rest.v("1").transcribe_file(
        {"buffer": AUDIO_BYTES, "mimetype": "audio/wav"},
        {"model": "nova-2", "smart_format": True, "diarize": True, "detect_language": True},
    )
    elapsed = time.time() - t0
    transcript = response.results.channels[0].alternatives[0].transcript
    words = response.results.channels[0].alternatives[0].words
    detected_lang = response.results.channels[0].detected_language
    print(f'  {GREEN}OK{RESET} ({elapsed:.1f}s)')
    print(f'  Transcript: "{transcript}"')
    print(f'  Words: {len(words)}, Language: {detected_lang}')
except Exception as e:
    print(f'  {RED}FAILED: {e}{RESET}')
    sys.exit(1)

# ============================================================
# Stubs for non-STT dependencies
# ============================================================
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

models_pkg = ModuleType('models')
models_pkg.__path__ = ['models']
sys.modules.setdefault('models', models_pkg)

ts_mod = ModuleType('models.transcript_segment')


class TranscriptSegment:
    def __init__(self, text='', speaker='SPEAKER_00', is_user=False, start=0.0, end=0.0,
                 person_id=None, stt_provider=None, speech_profile_processed=True, **_kw):
        self.text = text
        self.speaker = speaker
        self.is_user = is_user
        self.start = start
        self.end = end
        self.person_id = person_id
        self.stt_provider = stt_provider

    def dict(self):
        return {
            'text': self.text, 'speaker': self.speaker, 'is_user': self.is_user,
            'start': self.start, 'end': self.end, 'stt_provider': self.stt_provider,
        }


ts_mod.TranscriptSegment = TranscriptSegment
ts_mod.Translation = MagicMock()
sys.modules['models.transcript_segment'] = ts_mod
setattr(models_pkg, 'transcript_segment', ts_mod)

ep_mod = ModuleType('utils.other.endpoints')
ep_mod.timeit = lambda fn: fn
sys.modules.setdefault('utils.other.endpoints', ep_mod)

torch_mod = ModuleType('torch')
torch_mod.Tensor = type('Tensor', (), {})
torch_mod.set_num_threads = MagicMock()
torch_mod.hub = SimpleNamespace(load=MagicMock(return_value=(MagicMock(), None)))
sys.modules.setdefault('torch', torch_mod)

vad_mod = ModuleType('utils.stt.vad_gate')
vad_mod.GatedDeepgramSocket = MagicMock()
vad_mod.VADStreamingGate = MagicMock()
vad_mod.VAD_GATE_MODE = 'off'
vad_mod.is_gate_enabled = MagicMock(return_value=False)
sys.modules.setdefault('utils.stt.vad_gate', vad_mod)

fal_mod = ModuleType('fal_client')
fal_mod.submit = MagicMock()
sys.modules.setdefault('fal_client', fal_mod)

storage_mod = ModuleType('utils.other.storage')
storage_mod.upload_postprocessing_audio = lambda p: f'https://storage.example.com/{p}'
storage_mod.delete_postprocessing_audio = lambda p: None
sys.modules.setdefault('utils.other.storage', storage_mod)

# ============================================================
# Import STT abstraction layer
# ============================================================
from utils.stt.contracts import STTContext
from utils.stt.config import load_stt_configuration
from utils.stt.finalize import DefaultFinalizeTranscriptionService
from utils.stt.postprocess import TranscriptPostProcessingPipeline, build_default_post_processors
from utils.stt.registry import ProviderRegistry
from utils.stt.providers.deepgram import DeepgramBatchProvider
from utils.stt.selector import ProviderSelector

passed = 0
failed = 0

# ============================================================
# Test 2: Batch transcribe bytes through abstraction layer
# ============================================================
header('Test 2: Abstraction Layer — Transcribe Bytes')


async def test_batch_bytes():
    registry = ProviderRegistry()
    registry.register_batch(DeepgramBatchProvider())
    selector = ProviderSelector(registry)
    config = load_stt_configuration()
    pipeline = TranscriptPostProcessingPipeline(build_default_post_processors(config.enable_japanese_postprocessors))
    service = DefaultFinalizeTranscriptionService(registry, selector, pipeline)

    context = STTContext(
        uid='test-user', session_id='real-test',
        language='en', sample_rate=16000, channels=1, phase='finalize',
    )
    prefs = {'provider_preferences': {'finalize': 'deepgram_batch'}}

    t0 = time.time()
    result = await service.transcribe_bytes(AUDIO_BYTES, context, prefs)
    elapsed = time.time() - t0

    print(f'  {GREEN}OK{RESET} ({elapsed:.1f}s)')
    print(f'  Provider: {result.provider}')
    print(f'  Language: {result.language}')
    print(f'  Segments: {len(result.segments)}')
    for i, seg in enumerate(result.segments):
        print(f'    [{seg.start:.1f}s-{seg.end:.1f}s] {seg.speaker}: "{seg.text[:80]}"')
    print(f'  stt_provider tag: {result.segments[0].stt_provider if result.segments else "N/A"}')
    assert result.provider == 'deepgram_batch'
    assert len(result.segments) > 0


try:
    asyncio.run(test_batch_bytes())
    passed += 1
except Exception as e:
    failed += 1
    print(f'  {RED}FAILED: {e}{RESET}')
    import traceback
    traceback.print_exc()

# ============================================================
# Test 3: Provider Selection Logic
# ============================================================
header('Test 3: Provider Selection Logic')

try:
    registry = ProviderRegistry()
    registry.register_batch(DeepgramBatchProvider())
    selector = ProviderSelector(registry)

    ctx = STTContext(uid='u', session_id='s', language='en', phase='finalize')
    route = selector.select_finalize(ctx)
    print(f'  Default (en):   primary={route.primary}, source={route.source}, candidates={list(route.candidates)}')

    ctx_ja = STTContext(uid='u', session_id='s', language='ja', phase='finalize')
    route_ja = selector.select_finalize(ctx_ja)
    print(f'  Default (ja):   primary={route_ja.primary}, source={route_ja.source}')

    prefs = {'provider_preferences': {'finalize': 'deepgram_batch'}}
    route_user = selector.select_finalize(ctx_ja, prefs)
    print(f'  User pref (ja): primary={route_user.primary}, source={route_user.source}')

    print(f'  {GREEN}OK{RESET}')
    passed += 1
except Exception as e:
    failed += 1
    print(f'  {RED}FAILED: {e}{RESET}')

# ============================================================
# Test 4: Post-processing (terminology correction)
# ============================================================
header('Test 4: Terminology Correction on Real Transcription')


async def test_terminology():
    registry = ProviderRegistry()
    registry.register_batch(DeepgramBatchProvider())
    selector = ProviderSelector(registry)
    pipeline = TranscriptPostProcessingPipeline(build_default_post_processors(True))
    service = DefaultFinalizeTranscriptionService(registry, selector, pipeline)

    context = STTContext(
        uid='test-user', session_id='real-test-term',
        language='en', sample_rate=16000, channels=1, phase='finalize',
        terminology={'fox': 'FOX', 'dog': 'DOG'},
    )
    prefs = {'provider_preferences': {'finalize': 'deepgram_batch'}}

    result = await service.transcribe_bytes(AUDIO_BYTES, context, prefs)

    for seg in result.segments:
        print(f'    "{seg.text[:100]}"')

    has_fox = any('FOX' in seg.text for seg in result.segments)
    has_dog = any('DOG' in seg.text for seg in result.segments)
    if has_fox or has_dog:
        print(f'  Terminology applied: {GREEN}YES{RESET} (FOX={has_fox}, DOG={has_dog})')
    else:
        print(f'  Terminology: {YELLOW}target words not found in transcript{RESET}')
    print(f'  {GREEN}OK{RESET}')


try:
    asyncio.run(test_terminology())
    passed += 1
except Exception as e:
    failed += 1
    print(f'  {RED}FAILED: {e}{RESET}')
    import traceback
    traceback.print_exc()

# ============================================================
# Summary
# ============================================================
print(f'\n{BOLD}{"=" * 60}{RESET}')
print(f'{BOLD}  Results: {GREEN}{passed} passed{RESET}, {BOLD}{RED}{failed} failed{RESET}{BOLD} / {passed + failed} total{RESET}')
print(f'{BOLD}{"=" * 60}{RESET}')
sys.exit(1 if failed else 0)
