import asyncio
import os
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault('DEEPGRAM_API_KEY', 'fake-for-test')
os.environ.setdefault('STT_DEFAULT_REALTIME_PROVIDER', 'deepgram_streaming')
os.environ.setdefault('STT_DEFAULT_FINALIZE_PROVIDER', 'deepgram_batch')


def _install_stubs():
    models_pkg = ModuleType('models')
    models_pkg.__path__ = ['models']
    sys.modules.setdefault('models', models_pkg)

    transcript_segment_mod = ModuleType('models.transcript_segment')

    class TranscriptSegment:
        def __init__(
            self,
            text='',
            speaker='SPEAKER_00',
            is_user=False,
            start=0.0,
            end=0.0,
            person_id=None,
            stt_provider=None,
            speech_profile_processed=True,
            **_kwargs,
        ):
            self.text = text
            self.speaker = speaker
            self.is_user = is_user
            self.start = start
            self.end = end
            self.person_id = person_id
            self.stt_provider = stt_provider
            self.speech_profile_processed = speech_profile_processed

        @staticmethod
        def combine_segments(existing, new_segments, delta_seconds=0):
            return existing + new_segments, new_segments, []

    transcript_segment_mod.TranscriptSegment = TranscriptSegment
    transcript_segment_mod.Translation = MagicMock()
    sys.modules.setdefault('models.transcript_segment', transcript_segment_mod)
    setattr(models_pkg, 'transcript_segment', transcript_segment_mod)

    endpoints_mod = ModuleType('utils.other.endpoints')
    endpoints_mod.timeit = lambda fn: fn
    sys.modules.setdefault('utils.other.endpoints', endpoints_mod)

    fal_client_mod = ModuleType('fal_client')
    fal_client_mod.submit = MagicMock()
    sys.modules.setdefault('fal_client', fal_client_mod)

    torch_mod = ModuleType('torch')
    torch_mod.Tensor = type('Tensor', (), {})
    torch_mod.set_num_threads = MagicMock()
    torch_mod.hub = SimpleNamespace(load=MagicMock(return_value=(MagicMock(), None)))
    sys.modules.setdefault('torch', torch_mod)

    websockets_mod = ModuleType('websockets')
    websockets_mod.exceptions = SimpleNamespace(WebSocketException=Exception)
    sys.modules.setdefault('websockets', websockets_mod)

    vad_gate_mod = ModuleType('utils.stt.vad_gate')
    vad_gate_mod.GatedDeepgramSocket = MagicMock()
    vad_gate_mod.VADStreamingGate = MagicMock()
    vad_gate_mod.VAD_GATE_MODE = 'off'
    vad_gate_mod.is_gate_enabled = MagicMock(return_value=False)
    sys.modules.setdefault('utils.stt.vad_gate', vad_gate_mod)

    deepgram_mod = ModuleType('deepgram')

    class DeepgramClientOptions:
        def __init__(self, options=None):
            self.options = options or {}
            self.url = None

    class DeepgramClient:
        def __init__(self, *_args, **_kwargs):
            self.listen = SimpleNamespace(
                websocket=SimpleNamespace(v=lambda _version: MagicMock()),
                rest=SimpleNamespace(v=lambda _version: MagicMock()),
            )

    class LiveTranscriptionEvents:
        Transcript = 'Transcript'
        Error = 'Error'
        Close = 'Close'
        Open = 'Open'
        Metadata = 'Metadata'
        SpeechStarted = 'SpeechStarted'
        UtteranceEnd = 'UtteranceEnd'
        Unhandled = 'Unhandled'

    deepgram_mod.DeepgramClient = DeepgramClient
    deepgram_mod.DeepgramClientOptions = DeepgramClientOptions
    deepgram_mod.LiveTranscriptionEvents = LiveTranscriptionEvents
    sys.modules.setdefault('deepgram', deepgram_mod)

    deepgram_clients_mod = ModuleType('deepgram.clients')
    deepgram_clients_live_mod = ModuleType('deepgram.clients.live')
    deepgram_clients_live_v1_mod = ModuleType('deepgram.clients.live.v1')

    class LiveOptions:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    deepgram_clients_live_v1_mod.LiveOptions = LiveOptions
    sys.modules.setdefault('deepgram.clients', deepgram_clients_mod)
    sys.modules.setdefault('deepgram.clients.live', deepgram_clients_live_mod)
    sys.modules.setdefault('deepgram.clients.live.v1', deepgram_clients_live_v1_mod)


_install_stubs()

from models.transcript_segment import TranscriptSegment
from utils.stt.contracts import (
    BatchSTTProvider,
    BatchTranscriptionResult,
    ProviderCapabilities,
    STTContext,
    StreamingSTTProvider,
)
from utils.stt.finalize import DefaultFinalizeTranscriptionService
from utils.stt.postprocess import TranscriptPostProcessingPipeline
from utils.stt.providers.deepgram import DeepgramStreamingProvider
from utils.stt.registry import ProviderRegistry, build_default_provider_registry
from utils.stt.selector import ProviderSelector


class FakeStreamingSession:
    def __init__(self):
        self.sent = []
        self.finished = False
        self.is_connection_dead = False
        self.death_reason = None

    def send(self, audio: bytes) -> None:
        self.sent.append(audio)

    def finish(self) -> None:
        self.finished = True


class FakeBatchProvider(BatchSTTProvider):
    def __init__(self, name: str, result_text: str = 'hello', fail: bool = False):
        self.name = name
        self.aliases = ()
        self._result_text = result_text
        self._fail = fail
        self.capabilities = ProviderCapabilities(
            supports_streaming=False,
            supports_partial_results=False,
            supports_word_timestamps=True,
            supports_diarization=False,
            supports_confidence=False,
            supports_language_hint=True,
            supports_vocab_biasing=False,
            supports_endpointing=False,
        )

    async def transcribe_url(self, audio_url: str, context: STTContext) -> BatchTranscriptionResult:
        if self._fail:
            raise RuntimeError(f'{self.name} failed for {audio_url}')
        return BatchTranscriptionResult(
            provider=self.name,
            language=context.language,
            segments=[
                TranscriptSegment(
                    text=self._result_text,
                    speaker='SPEAKER_00',
                    is_user=False,
                    start=0.0,
                    end=1.0,
                    stt_provider=self.name,
                )
            ],
            metadata={'mode': 'url'},
        )

    async def transcribe_bytes(self, audio_bytes: bytes, context: STTContext) -> BatchTranscriptionResult:
        if self._fail:
            raise RuntimeError(f'{self.name} failed for bytes')
        return BatchTranscriptionResult(
            provider=self.name,
            language=context.language,
            segments=[
                TranscriptSegment(
                    text=self._result_text,
                    speaker='SPEAKER_00',
                    is_user=False,
                    start=0.0,
                    end=1.0,
                    stt_provider=self.name,
                )
            ],
            metadata={'mode': 'bytes'},
        )


class RecordingPostProcessor:
    def __init__(self, name: str, calls: list):
        self.name = name
        self.calls = calls

    def supports(self, context: STTContext) -> bool:
        return True

    async def process(self, segments, context: STTContext):
        self.calls.append(self.name)
        for segment in segments:
            segment.text += f'|{self.name}'
        return segments


class TestSTTProviderAbstraction(unittest.TestCase):
    def test_provider_registry_registers_default_providers(self):
        registry = build_default_provider_registry()

        self.assertEqual(registry.get_streaming('deepgram_streaming').name, 'deepgram_streaming')
        self.assertEqual(registry.get_streaming('deepgram').name, 'deepgram_streaming')
        self.assertEqual(registry.get_streaming('whisper_streaming').name, 'whisper_streaming')
        self.assertEqual(registry.get_batch('deepgram_batch').name, 'deepgram_batch')
        self.assertEqual(registry.get_batch('whisper_batch').name, 'whisper_batch')

    def test_provider_selector_prefers_user_override_and_preserves_fallbacks(self):
        with patch.dict(
            os.environ,
            {
                'STT_DEFAULT_REALTIME_PROVIDER': 'deepgram_streaming',
                'STT_PROVIDER_FALLBACK_CHAIN': '{"realtime":["whisper_streaming"]}',
            },
            clear=False,
        ):
            selector = ProviderSelector()
            context = STTContext(uid='user-1', session_id='session-1', language='ja')
            prefs = {
                'provider_preferences': {
                    'realtime': 'whisper_streaming',
                    'fallbacks': {'realtime': ['deepgram_streaming']},
                }
            }

            route = selector.select_realtime(context, prefs)

        self.assertEqual(route.primary, 'whisper_streaming')
        self.assertEqual(list(route.candidates), ['whisper_streaming', 'deepgram_streaming'])
        self.assertEqual(route.source, 'user')

    def test_config_based_provider_override_resolution(self):
        with patch.dict(
            os.environ,
            {
                'STT_DEFAULT_FINALIZE_PROVIDER': 'deepgram_batch',
                'STT_LANGUAGE_PROVIDER_OVERRIDES': '{"ja":{"finalize":"whisper_batch"}}',
                'STT_PROVIDER_FALLBACK_CHAIN': '{"finalize":["deepgram_batch"]}',
            },
            clear=False,
        ):
            selector = ProviderSelector()
            context = STTContext(uid='user-1', session_id='session-1', language='ja-JP', phase='finalize')
            route = selector.select_finalize(context)

        self.assertEqual(route.primary, 'whisper_batch')
        self.assertEqual(list(route.candidates), ['whisper_batch', 'deepgram_batch'])
        self.assertEqual(route.source, 'language')

    def test_deepgram_provider_contract_emits_stt_events(self):
        provider = DeepgramStreamingProvider()
        context = STTContext(uid='user-1', session_id='session-1', language='ja', sample_rate=16000, channels=1)
        fake_session = FakeStreamingSession()
        events = []

        with patch(
            'utils.stt.providers.deepgram.get_stt_service_for_language',
            return_value=('deepgram', 'multi', 'nova-3'),
        ):
            with patch(
                'utils.stt.providers.deepgram.process_audio_dg', new=AsyncMock(return_value=fake_session)
            ) as mock_dg:
                session = asyncio.run(provider.open_stream(context, sink=events.append, is_active=lambda: True))

        self.assertIs(session, fake_session)
        callback = mock_dg.await_args.args[0]
        callback(
            [
                {
                    'speaker': 'SPEAKER_00',
                    'start': 0.0,
                    'end': 1.0,
                    'text': 'hello',
                    'is_user': False,
                    'person_id': None,
                }
            ]
        )

        self.assertTrue(events)
        self.assertEqual(events[0].provider, 'deepgram_streaming')
        self.assertEqual(events[0].segments[0]['stt_provider'], 'deepgram_streaming')
        self.assertEqual(events[0].metadata['language'], 'multi')

    def test_postprocessing_pipeline_execution_order(self):
        calls = []
        pipeline = TranscriptPostProcessingPipeline(
            [
                RecordingPostProcessor('first', calls),
                RecordingPostProcessor('second', calls),
            ]
        )
        segments = [
            TranscriptSegment(
                text='hello',
                speaker='SPEAKER_00',
                is_user=False,
                start=0.0,
                end=1.0,
            )
        ]
        context = STTContext(uid='user-1', session_id='session-1', language='en')

        processed = asyncio.run(pipeline.process(segments, context))

        self.assertEqual(calls, ['first', 'second'])
        self.assertEqual(processed[0].text, 'hello|first|second')

    def test_finalize_service_falls_back_to_next_provider(self):
        registry = ProviderRegistry()
        registry.register_batch(FakeBatchProvider('whisper_batch', fail=True))
        registry.register_batch(FakeBatchProvider('deepgram_batch', result_text='fallback'))
        selector = ProviderSelector(registry)
        pipeline = TranscriptPostProcessingPipeline([])
        service = DefaultFinalizeTranscriptionService(registry, selector, pipeline)
        context = STTContext(uid='user-1', session_id='session-1', language='ja', phase='finalize')

        with patch.dict(
            os.environ,
            {
                'STT_DEFAULT_FINALIZE_PROVIDER': 'whisper_batch',
                'STT_PROVIDER_FALLBACK_CHAIN': '{"finalize":["deepgram_batch"]}',
            },
            clear=False,
        ):
            result = asyncio.run(
                service.transcribe_url(
                    'https://example.com/audio.wav',
                    context,
                    transcription_prefs={
                        'provider_preferences': {
                            'finalize': 'whisper_batch',
                            'fallbacks': {'finalize': ['deepgram_batch']},
                        }
                    },
                )
            )

        self.assertEqual(result.provider, 'deepgram_batch')
        self.assertEqual(result.segments[0].text, 'fallback')

    def test_finalize_service_transcribe_bytes_with_fallback(self):
        registry = ProviderRegistry()
        registry.register_batch(FakeBatchProvider('whisper_batch', fail=True))
        registry.register_batch(FakeBatchProvider('deepgram_batch', result_text='bytes_fallback'))
        selector = ProviderSelector(registry)
        pipeline = TranscriptPostProcessingPipeline([])
        service = DefaultFinalizeTranscriptionService(registry, selector, pipeline)
        context = STTContext(uid='user-1', session_id='session-1', language='en', phase='finalize')

        with patch.dict(
            os.environ,
            {
                'STT_DEFAULT_FINALIZE_PROVIDER': 'whisper_batch',
                'STT_PROVIDER_FALLBACK_CHAIN': '{"finalize":["deepgram_batch"]}',
            },
            clear=False,
        ):
            result = asyncio.run(
                service.transcribe_bytes(
                    b'fake-audio-bytes',
                    context,
                    transcription_prefs={
                        'provider_preferences': {
                            'finalize': 'whisper_batch',
                            'fallbacks': {'finalize': ['deepgram_batch']},
                        }
                    },
                )
            )

        self.assertEqual(result.provider, 'deepgram_batch')
        self.assertEqual(result.segments[0].text, 'bytes_fallback')

    def test_factory_builds_finalize_service(self):
        storage_mod = MagicMock()
        sys.modules['utils.other.storage'] = storage_mod

        from utils.stt.factory import build_finalize_service

        with patch.dict(
            os.environ,
            {
                'STT_DEFAULT_FINALIZE_PROVIDER': 'deepgram_batch',
            },
            clear=False,
        ):
            service = build_finalize_service()

        self.assertIsInstance(service, DefaultFinalizeTranscriptionService)
        self.assertIsNotNone(service.registry)
        self.assertIsNotNone(service.selector)
        self.assertIsNotNone(service.post_processing_pipeline)


if __name__ == '__main__':
    unittest.main()
