"""
Lightweight demo server for the STT Provider Abstraction Layer.

Runs without Firebase, Redis, or any heavy dependencies.
Tests the core abstraction: registry, selector, finalize service, streaming session.

Usage:
    cd backend
    source .venv/bin/activate
    python demo_stt_server.py

Endpoints:
    GET  /health                 - Health check
    GET  /providers              - List registered providers
    POST /transcribe/url         - Batch transcribe from URL (through abstraction)
    POST /transcribe/bytes       - Batch transcribe from uploaded audio bytes
    WS   /ws/listen              - WebSocket streaming (simulated with mock provider)
    POST /select                 - Show provider selection decision for given params
"""

import asyncio
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from typing import List, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
logger = logging.getLogger('demo_stt')

# --- Stub heavy dependencies that the STT layer transitively imports ---

from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock


def _install_stubs():
    """Install minimal stubs so stt modules import without heavy deps."""

    # models.transcript_segment
    models_pkg = sys.modules.get('models') or ModuleType('models')
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
            self.speech_profile_processed = speech_profile_processed

        def dict(self):
            return {
                'text': self.text, 'speaker': self.speaker, 'is_user': self.is_user,
                'start': self.start, 'end': self.end, 'person_id': self.person_id,
                'stt_provider': self.stt_provider,
            }

        @staticmethod
        def combine_segments(existing, new_segments, delta_seconds=0):
            return existing + new_segments, new_segments, []

    ts_mod.TranscriptSegment = TranscriptSegment
    ts_mod.Translation = MagicMock()
    sys.modules['models.transcript_segment'] = ts_mod
    setattr(models_pkg, 'transcript_segment', ts_mod)

    # utils.other.endpoints
    ep_mod = ModuleType('utils.other.endpoints')
    ep_mod.timeit = lambda fn: fn
    sys.modules.setdefault('utils.other.endpoints', ep_mod)

    # torch (for vad_gate transitive import)
    torch_mod = ModuleType('torch')
    torch_mod.Tensor = type('Tensor', (), {})
    torch_mod.set_num_threads = MagicMock()
    torch_mod.hub = SimpleNamespace(load=MagicMock(return_value=(MagicMock(), None)))
    sys.modules.setdefault('torch', torch_mod)

    # websockets — do NOT stub; real package is installed and uvicorn needs it

    # deepgram
    dg_mod = ModuleType('deepgram')

    class DgClientOpts:
        def __init__(self, options=None):
            self.options = options or {}
            self.url = None

    class DgClient:
        def __init__(self, *a, **kw):
            self.listen = SimpleNamespace(
                websocket=SimpleNamespace(v=lambda _: MagicMock()),
                rest=SimpleNamespace(v=lambda _: MagicMock()),
            )

    class LiveEvents:
        Transcript = 'Transcript'
        Error = 'Error'
        Close = 'Close'
        Open = 'Open'
        Metadata = 'Metadata'
        SpeechStarted = 'SpeechStarted'
        UtteranceEnd = 'UtteranceEnd'
        Unhandled = 'Unhandled'

    dg_mod.DeepgramClient = DgClient
    dg_mod.DeepgramClientOptions = DgClientOpts
    dg_mod.LiveTranscriptionEvents = LiveEvents
    sys.modules.setdefault('deepgram', dg_mod)

    dg_live_v1 = ModuleType('deepgram.clients.live.v1')

    class LiveOptions:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    dg_live_v1.LiveOptions = LiveOptions
    sys.modules.setdefault('deepgram.clients', ModuleType('deepgram.clients'))
    sys.modules.setdefault('deepgram.clients.live', ModuleType('deepgram.clients.live'))
    sys.modules.setdefault('deepgram.clients.live.v1', dg_live_v1)

    # fal_client
    fal_mod = ModuleType('fal_client')
    fal_mod.submit = MagicMock()
    sys.modules.setdefault('fal_client', fal_mod)

    # vad_gate
    vad_mod = ModuleType('utils.stt.vad_gate')
    vad_mod.GatedDeepgramSocket = MagicMock()
    vad_mod.VADStreamingGate = MagicMock()
    vad_mod.VAD_GATE_MODE = 'off'
    vad_mod.is_gate_enabled = MagicMock(return_value=False)
    sys.modules.setdefault('utils.stt.vad_gate', vad_mod)

    # utils.other.storage (for whisper bytes staging)
    storage_mod = ModuleType('utils.other.storage')
    storage_mod.upload_postprocessing_audio = lambda path: f'https://storage.example.com/{os.path.basename(path)}'
    storage_mod.delete_postprocessing_audio = lambda path: None
    sys.modules.setdefault('utils.other.storage', storage_mod)


_install_stubs()

# --- Now safe to import STT abstraction layer ---

from utils.stt.contracts import (
    BatchSTTProvider,
    BatchTranscriptionResult,
    ProviderCapabilities,
    STTContext,
    STTEvent,
    STTEventType,
    StreamingSTTProvider,
)
from utils.stt.config import load_stt_configuration
from utils.stt.finalize import DefaultFinalizeTranscriptionService
from utils.stt.postprocess import TranscriptPostProcessingPipeline, build_default_post_processors
from utils.stt.registry import ProviderRegistry
from utils.stt.selector import ProviderSelector
from utils.stt.runtime import open_realtime_stt_session

from models.transcript_segment import TranscriptSegment

# ============================================================
# Mock Providers (simulate real STT without API keys)
# ============================================================


class MockStreamingSession:
    """Simulates a streaming STT session."""

    def __init__(self, sink, provider_name, language):
        self.sink = sink
        self.provider_name = provider_name
        self.language = language
        self.is_connection_dead = False
        self.death_reason = None
        self._chunk_count = 0

    def send(self, audio: bytes) -> None:
        self._chunk_count += 1
        if self._chunk_count % 5 == 0:
            self.sink(
                STTEvent(
                    provider=self.provider_name,
                    event_type=STTEventType.final,
                    segments=[{
                        'text': f'[Mock transcript chunk {self._chunk_count // 5}]',
                        'speaker': 'SPEAKER_00',
                        'start': (self._chunk_count - 5) * 0.1,
                        'end': self._chunk_count * 0.1,
                        'is_user': False,
                        'person_id': None,
                        'stt_provider': self.provider_name,
                    }],
                    is_final=True,
                    metadata={'language': self.language},
                )
            )

    def finish(self) -> None:
        self.is_connection_dead = True


class MockStreamingProvider(StreamingSTTProvider):
    name = 'mock_streaming'
    aliases = ('mock',)
    capabilities = ProviderCapabilities(
        supports_streaming=True, supports_partial_results=True,
        supports_word_timestamps=True, supports_diarization=False,
        supports_confidence=False, supports_language_hint=True,
        supports_vocab_biasing=False, supports_endpointing=False,
    )

    async def open_stream(self, context, sink, vad_gate=None, is_active=None):
        logger.info('MockStreamingProvider.open_stream language=%s uid=%s', context.language, context.uid)
        return MockStreamingSession(sink, self.name, context.language)


class MockBatchProvider(BatchSTTProvider):
    name = 'mock_batch'
    aliases = ('mock_prerecorded',)
    capabilities = ProviderCapabilities(
        supports_streaming=False, supports_partial_results=False,
        supports_word_timestamps=True, supports_diarization=True,
        supports_confidence=False, supports_language_hint=True,
        supports_vocab_biasing=False, supports_endpointing=False,
    )

    async def transcribe_url(self, audio_url, context):
        logger.info('MockBatchProvider.transcribe_url url=%s lang=%s', audio_url, context.language)
        await asyncio.sleep(0.1)  # simulate latency
        segments = [
            TranscriptSegment(
                text='This is a mock transcription from the STT provider abstraction layer.',
                speaker='SPEAKER_00', is_user=False, start=0.0, end=3.5, stt_provider=self.name,
            ),
            TranscriptSegment(
                text='The provider selection, fallback, and post-processing pipeline all work correctly.',
                speaker='SPEAKER_01', is_user=True, start=3.5, end=7.2, stt_provider=self.name,
            ),
        ]
        return BatchTranscriptionResult(
            provider=self.name, language=context.language,
            segments=segments, metadata={'source': 'mock', 'url': audio_url},
        )

    async def transcribe_bytes(self, audio_bytes, context):
        logger.info('MockBatchProvider.transcribe_bytes len=%d lang=%s', len(audio_bytes), context.language)
        await asyncio.sleep(0.1)
        segments = [
            TranscriptSegment(
                text=f'Mock transcription from {len(audio_bytes)} bytes of audio.',
                speaker='SPEAKER_00', is_user=False, start=0.0, end=2.0, stt_provider=self.name,
            ),
        ]
        return BatchTranscriptionResult(
            provider=self.name, language=context.language,
            segments=segments, metadata={'source': 'mock_bytes', 'bytes_len': len(audio_bytes)},
        )


# ============================================================
# Build registry with mock providers
# ============================================================

def build_demo_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register_streaming(MockStreamingProvider())
    registry.register_batch(MockBatchProvider())
    return registry


def build_demo_finalize_service(registry, transcription_prefs=None):
    selector = ProviderSelector(registry)
    config = load_stt_configuration(transcription_prefs)
    pipeline = TranscriptPostProcessingPipeline(
        build_default_post_processors(config.enable_japanese_postprocessors)
    )
    return DefaultFinalizeTranscriptionService(registry, selector, pipeline)


# ============================================================
# FastAPI App
# ============================================================

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title='STT Provider Abstraction Demo', version='0.1.0')

# Set env defaults so selector picks mock providers
os.environ.setdefault('STT_DEFAULT_REALTIME_PROVIDER', 'mock_streaming')
os.environ.setdefault('STT_DEFAULT_FINALIZE_PROVIDER', 'mock_batch')

_registry = build_demo_registry()


@app.get('/health')
async def health():
    return {'status': 'ok', 'providers': {
        'streaming': _registry.list_streaming(),
        'batch': _registry.list_batch(),
    }}


@app.get('/providers')
async def list_providers():
    streaming = []
    for name in _registry.list_streaming():
        p = _registry.get_streaming(name)
        streaming.append({
            'name': p.name, 'aliases': list(p.aliases),
            'capabilities': asdict(p.capabilities),
        })
    batch = []
    for name in _registry.list_batch():
        p = _registry.get_batch(name)
        batch.append({
            'name': p.name, 'aliases': list(p.aliases),
            'capabilities': asdict(p.capabilities),
        })
    return {'streaming': streaming, 'batch': batch}


class TranscribeURLRequest(BaseModel):
    audio_url: str
    language: str = 'en'
    uid: str = 'demo-user'
    provider_hint: Optional[str] = None
    terminology: dict = {}


@app.post('/transcribe/url')
async def transcribe_url(req: TranscribeURLRequest):
    prefs = {}
    if req.provider_hint:
        prefs['provider_preferences'] = {'finalize': req.provider_hint}

    service = build_demo_finalize_service(_registry, prefs)
    context = STTContext(
        uid=req.uid, session_id='demo-session',
        language=req.language, phase='finalize',
        terminology=req.terminology,
    )
    result = await service.transcribe_url(req.audio_url, context, prefs)
    return {
        'provider': result.provider,
        'language': result.language,
        'segments': [s.dict() for s in result.segments],
        'metadata': dict(result.metadata),
    }


class TranscribeBytesRequest(BaseModel):
    language: str = 'en'
    uid: str = 'demo-user'


@app.post('/transcribe/bytes')
async def transcribe_bytes(req: TranscribeBytesRequest):
    # In a real app, this would accept multipart form data with the audio file.
    # For demo, we simulate with synthetic bytes.
    fake_audio = b'\x00' * 16000 * 2  # 1 second of 16kHz 16-bit silence

    service = build_demo_finalize_service(_registry)
    context = STTContext(
        uid=req.uid, session_id='demo-session',
        language=req.language, phase='finalize',
    )
    result = await service.transcribe_bytes(fake_audio, context)
    return {
        'provider': result.provider,
        'language': result.language,
        'segments': [s.dict() for s in result.segments],
        'metadata': dict(result.metadata),
    }


class SelectRequest(BaseModel):
    phase: str = 'realtime'
    language: str = 'en'
    provider_hint: Optional[str] = None
    user_preference: Optional[str] = None


@app.post('/select')
async def select_provider(req: SelectRequest):
    selector = ProviderSelector(_registry)
    context = STTContext(
        uid='demo-user', session_id='demo',
        language=req.language, provider_hint=req.provider_hint,
        phase=req.phase,
    )
    prefs = {}
    if req.user_preference:
        prefs['provider_preferences'] = {req.phase: req.user_preference}

    if req.phase == 'realtime':
        route = selector.select_realtime(context, prefs)
    else:
        route = selector.select_finalize(context, prefs)

    return {
        'phase': route.phase,
        'primary': route.primary,
        'candidates': list(route.candidates),
        'source': route.source,
        'language': route.language,
    }


@app.websocket('/ws/listen')
async def ws_listen(websocket: WebSocket):
    await websocket.accept()
    logger.info('WebSocket client connected')

    # Parse initial config from query params
    language = websocket.query_params.get('language', 'en')
    uid = websocket.query_params.get('uid', 'demo-user')
    provider_hint = websocket.query_params.get('provider', None)

    selector = ProviderSelector(_registry)
    events_buffer: List[dict] = []

    def on_stt_event(event: STTEvent):
        for seg in event.segments:
            events_buffer.append({
                'provider': event.provider,
                'type': event.event_type.value,
                'segment': seg if isinstance(seg, dict) else seg.dict(),
            })

    try:
        context = STTContext(
            uid=uid, session_id='ws-demo',
            language=language, provider_hint=provider_hint,
        )
        handle = await open_realtime_stt_session(
            _registry, selector, context, sink=on_stt_event,
        )

        await websocket.send_json({
            'type': 'connected',
            'provider': handle.provider_name,
            'route': {
                'primary': handle.route.primary,
                'candidates': list(handle.route.candidates),
                'source': handle.route.source,
            },
        })

        while True:
            data = await websocket.receive_bytes()
            handle.session.send(data)

            if events_buffer:
                for evt in events_buffer:
                    await websocket.send_json(evt)
                events_buffer.clear()

    except WebSocketDisconnect:
        logger.info('WebSocket client disconnected')
    except Exception as e:
        logger.error('WebSocket error: %s', e)
        await websocket.close(code=1011, reason=str(e))


# ============================================================
# Entry point
# ============================================================

if __name__ == '__main__':
    import uvicorn

    port = int(os.environ.get('DEMO_PORT', '8090'))
    logger.info('Starting STT demo server on port %d', port)
    logger.info('Endpoints:')
    logger.info('  GET  http://localhost:%d/health', port)
    logger.info('  GET  http://localhost:%d/providers', port)
    logger.info('  POST http://localhost:%d/transcribe/url', port)
    logger.info('  POST http://localhost:%d/transcribe/bytes', port)
    logger.info('  POST http://localhost:%d/select', port)
    logger.info('  WS   ws://localhost:%d/ws/listen', port)
    uvicorn.run(app, host='0.0.0.0', port=port, log_level='info')
