import logging
from dataclasses import dataclass
from typing import Callable, Optional

from utils.stt.contracts import STTContext, STTEvent, StreamingSTTSession
from utils.stt.registry import ProviderRegistry
from utils.stt.selector import ProviderRoute, ProviderSelector

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RealtimeProviderHandle:
    provider_name: str
    route: ProviderRoute
    session: StreamingSTTSession


async def open_realtime_stt_session(
    registry: ProviderRegistry,
    selector: ProviderSelector,
    context: STTContext,
    sink: Callable[[STTEvent], None],
    transcription_prefs: Optional[dict] = None,
    vad_gate=None,
    is_active: Optional[Callable[[], bool]] = None,
) -> RealtimeProviderHandle:
    route = selector.select_realtime(context, transcription_prefs)
    last_error = None

    for provider_name in route.candidates:
        provider = registry.get_streaming(provider_name)
        if provider is None:
            logger.warning('Streaming STT provider not registered: %s', provider_name)
            continue

        try:
            session = await provider.open_stream(context, sink=sink, vad_gate=vad_gate, is_active=is_active)
            logger.info(
                'Realtime STT provider selected provider=%s source=%s language=%s',
                provider.name,
                route.source,
                route.language,
            )
            return RealtimeProviderHandle(provider_name=provider.name, route=route, session=session)
        except Exception as exc:
            last_error = exc
            logger.warning('Realtime STT provider failed provider=%s error=%s', provider_name, exc)

    if last_error:
        raise RuntimeError(f'Could not initialize any realtime STT provider: {last_error}') from last_error
    raise RuntimeError('Could not initialize any realtime STT provider')
