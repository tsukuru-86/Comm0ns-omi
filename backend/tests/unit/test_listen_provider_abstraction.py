import asyncio
import importlib
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock


def _install_transcribe_stubs():
    fastapi_mod = ModuleType('fastapi')

    class APIRouter:
        def websocket(self, _path):
            def decorator(func):
                return func

            return decorator

    def Depends(dependency):
        return dependency

    def Header(default=None):
        return default

    fastapi_mod.APIRouter = APIRouter
    fastapi_mod.Depends = Depends
    fastapi_mod.Header = Header
    sys.modules.setdefault('fastapi', fastapi_mod)

    fastapi_websockets_mod = ModuleType('fastapi.websockets')
    fastapi_websockets_mod.WebSocket = object
    fastapi_websockets_mod.WebSocketDisconnect = Exception
    sys.modules.setdefault('fastapi.websockets', fastapi_websockets_mod)

    starlette_websockets_mod = ModuleType('starlette.websockets')
    starlette_websockets_mod.WebSocketState = SimpleNamespace(CONNECTED='connected')
    sys.modules.setdefault('starlette.websockets', starlette_websockets_mod)

    sys.modules.setdefault('numpy', MagicMock())
    websockets_mod = ModuleType('websockets')
    websockets_exceptions_mod = ModuleType('websockets.exceptions')
    websockets_exceptions_mod.ConnectionClosed = Exception
    websockets_mod.exceptions = websockets_exceptions_mod
    sys.modules.setdefault('websockets', websockets_mod)
    sys.modules.setdefault('websockets.exceptions', websockets_exceptions_mod)

    av_mod = ModuleType('av')
    sys.modules.setdefault('av', av_mod)

    opuslib_mod = ModuleType('opuslib')
    opuslib_mod.Decoder = MagicMock()
    sys.modules.setdefault('opuslib', opuslib_mod)

    lc3_mod = ModuleType('lc3')
    lc3_mod.Decoder = MagicMock()
    sys.modules.setdefault('lc3', lc3_mod)

    fal_client_mod = ModuleType('fal_client')
    fal_client_mod.submit = MagicMock()
    sys.modules.setdefault('fal_client', fal_client_mod)

    deepgram_mod = ModuleType('deepgram')

    class DeepgramClientOptions:
        def __init__(self, options=None):
            self.options = options or {}
            self.url = None

    class DeepgramClient:
        def __init__(self, *_args, **_kwargs):
            self.listen = SimpleNamespace(rest=SimpleNamespace(v=lambda _version: MagicMock()))

    deepgram_mod.DeepgramClient = DeepgramClient
    deepgram_mod.DeepgramClientOptions = DeepgramClientOptions
    sys.modules.setdefault('deepgram', deepgram_mod)

    firebase_admin_mod = ModuleType('firebase_admin')
    firebase_admin_auth_mod = ModuleType('firebase_admin.auth')

    class InvalidIdTokenError(Exception):
        pass

    firebase_admin_auth_mod.InvalidIdTokenError = InvalidIdTokenError
    firebase_admin_mod.auth = firebase_admin_auth_mod
    sys.modules.setdefault('firebase_admin', firebase_admin_mod)
    sys.modules.setdefault('firebase_admin.auth', firebase_admin_auth_mod)

    database_pkg = ModuleType('database')
    database_pkg.__path__ = ['database']
    sys.modules.setdefault('database', database_pkg)

    for submodule in ['conversations', 'calendar_meetings', 'users', 'redis_db']:
        full_name = f'database.{submodule}'
        mod = MagicMock()
        sys.modules.setdefault(full_name, mod)
        setattr(database_pkg, submodule, mod)

    database_users_mod = sys.modules['database.users']
    database_users_mod.get_user_transcription_preferences.return_value = {
        'single_language_mode': False,
        'vocabulary': [],
        'language': 'en',
        'provider_preferences': {},
        'terminology': {},
        'enable_ja_filler_cleanup': False,
    }

    models_pkg = ModuleType('models')
    models_pkg.__path__ = ['models']
    sys.modules.setdefault('models', models_pkg)

    conversation_mod = ModuleType('models.conversation')
    conversation_mod.Conversation = MagicMock()
    conversation_mod.ConversationPhoto = MagicMock()
    conversation_mod.Structured = MagicMock()
    conversation_mod.TranscriptSegment = MagicMock()
    conversation_mod.ConversationSource = SimpleNamespace(omi='omi')
    conversation_mod.ConversationStatus = SimpleNamespace(in_progress='in_progress')
    sys.modules.setdefault('models.conversation', conversation_mod)
    setattr(models_pkg, 'conversation', conversation_mod)

    message_event_mod = ModuleType('models.message_event')
    for name in [
        'ConversationEvent',
        'FreemiumThresholdReachedEvent',
        'LastConversationEvent',
        'MessageEvent',
        'MessageServiceStatusEvent',
        'PhotoDescribedEvent',
        'PhotoProcessingEvent',
        'SegmentsDeletedEvent',
        'SpeakerLabelSuggestionEvent',
        'TranslationEvent',
    ]:
        setattr(message_event_mod, name, MagicMock())
    message_event_mod.FREEMIUM_ACTION_SETUP_ON_DEVICE_STT = 'setup'
    sys.modules.setdefault('models.message_event', message_event_mod)
    setattr(models_pkg, 'message_event', message_event_mod)

    transcript_segment_mod = ModuleType('models.transcript_segment')
    transcript_segment_mod.TranscriptSegment = MagicMock()
    transcript_segment_mod.Translation = MagicMock()
    sys.modules.setdefault('models.transcript_segment', transcript_segment_mod)
    setattr(models_pkg, 'transcript_segment', transcript_segment_mod)

    users_model_mod = ModuleType('models.users')
    users_model_mod.PlanType = SimpleNamespace(basic='basic')
    sys.modules.setdefault('models.users', users_model_mod)
    setattr(models_pkg, 'users', users_model_mod)

    endpoints_mod = sys.modules.get('utils.other.endpoints', ModuleType('utils.other.endpoints'))

    def get_current_user_uid_ws_listen(authorization: str = Header(None)):
        return 'route-test-user'

    def get_current_user_uid_from_ws_message(_message):
        return 'route-test-user'

    endpoints_mod.get_current_user_uid_ws_listen = get_current_user_uid_ws_listen
    endpoints_mod.get_current_user_uid_from_ws_message = get_current_user_uid_from_ws_message
    endpoints_mod.timeit = lambda fn: fn
    sys.modules['utils.other.endpoints'] = endpoints_mod

    simple_utils = [
        'utils.speaker_assignment',
        'utils.analytics',
        'utils.app_integrations',
        'utils.apps',
        'utils.conversations.process_conversation',
        'utils.notifications',
        'utils.other.storage',
        'utils.pusher',
        'utils.speaker_identification',
        'utils.stt.streaming',
        'utils.stt.vad_gate',
        'utils.fair_use',
        'utils.subscription',
        'utils.translation',
        'utils.translation_cache',
        'utils.translation_coordinator',
        'utils.webhooks',
        'utils.onboarding',
        'utils.aac',
        'utils.audio',
        'utils.metrics',
        'utils.stt.speaker_embedding',
        'utils.speaker_sample_migration',
        'utils.log_sanitizer',
    ]

    for module_name in simple_utils:
        sys.modules.setdefault(module_name, MagicMock())


_install_transcribe_stubs()

from utils.stt.contracts import ProviderCapabilities, STTContext, STTEvent, STTEventType, StreamingSTTProvider
from utils.stt.registry import ProviderRegistry
from utils.stt.runtime import open_realtime_stt_session
from utils.stt.selector import ProviderSelector


class DummySession:
    is_connection_dead = False
    death_reason = None

    def send(self, _audio: bytes) -> None:
        return None

    def finish(self) -> None:
        return None


class FakeWebSocket:
    def __init__(self):
        self.accepted = False
        self.client_state = 'connected'
        self.sent_json = []
        self.close_code = None
        self.close_reason = None

    async def accept(self):
        self.accepted = True

    async def send_json(self, payload):
        self.sent_json.append(payload)

    async def close(self, code=1000, reason=None):
        self.close_code = code
        self.close_reason = reason


class DummyStreamingProvider(StreamingSTTProvider):
    name = 'dummy_streaming'
    aliases = ()
    capabilities = ProviderCapabilities(
        supports_streaming=True,
        supports_partial_results=False,
        supports_word_timestamps=False,
        supports_diarization=False,
        supports_confidence=False,
        supports_language_hint=True,
        supports_vocab_biasing=False,
        supports_endpointing=False,
    )

    async def open_stream(self, context: STTContext, sink, vad_gate=None, is_active=None):
        sink(
            STTEvent(
                provider=self.name,
                event_type=STTEventType.status,
                segments=[{'text': 'ready'}],
                metadata={'provider_hint': context.provider_hint or ''},
            )
        )
        return DummySession()


class TestListenProviderAbstraction(unittest.TestCase):
    def test_listen_route_passes_provider_hint_into_abstraction(self):
        transcribe = importlib.import_module('routers.transcribe')

        async def lightweight_stream_handler(
            websocket,
            uid,
            language='en',
            sample_rate=8000,
            codec='pcm8',
            channels=1,
            include_speech_profile=True,
            stt_service=None,
            conversation_timeout=120,
            source=None,
            custom_stt_mode=None,
            onboarding_mode=False,
            speaker_auto_assign_enabled=False,
            vad_gate_override=None,
            call_id=None,
        ):
            registry = ProviderRegistry()
            registry.register_streaming(DummyStreamingProvider())
            selector = ProviderSelector(registry)
            events = []
            await open_realtime_stt_session(
                registry,
                selector,
                STTContext(
                    uid=uid,
                    session_id='listen-route-test',
                    language=language,
                    sample_rate=sample_rate,
                    channels=1,
                    provider_hint=stt_service,
                ),
                sink=events.append,
            )
            await websocket.send_json(
                {
                    'uid': uid,
                    'provider': events[0].provider,
                    'provider_hint': events[0].metadata['provider_hint'],
                }
            )
            await websocket.close()

        transcribe._stream_handler = lightweight_stream_handler
        websocket = FakeWebSocket()

        asyncio.run(
            transcribe.listen_handler(
                websocket,
                uid='route-test-user',
                stt_service='dummy_streaming',
            )
        )

        self.assertTrue(websocket.accepted)
        self.assertEqual(websocket.sent_json[0]['uid'], 'route-test-user')
        self.assertEqual(websocket.sent_json[0]['provider'], 'dummy_streaming')
        self.assertEqual(websocket.sent_json[0]['provider_hint'], 'dummy_streaming')


if __name__ == '__main__':
    unittest.main()
