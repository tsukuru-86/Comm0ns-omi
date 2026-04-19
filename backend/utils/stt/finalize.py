import logging
from dataclasses import replace
from typing import Optional

from utils.stt.contracts import BatchTranscriptionResult, FinalizeTranscriptionService, STTContext
from utils.stt.postprocess import TranscriptPostProcessingPipeline
from utils.stt.registry import ProviderRegistry
from utils.stt.selector import ProviderSelector

logger = logging.getLogger(__name__)


class DefaultFinalizeTranscriptionService(FinalizeTranscriptionService):
    def __init__(
        self,
        registry: ProviderRegistry,
        selector: ProviderSelector,
        post_processing_pipeline: TranscriptPostProcessingPipeline,
    ):
        self.registry = registry
        self.selector = selector
        self.post_processing_pipeline = post_processing_pipeline

    async def transcribe_url(
        self, audio_url: str, context: STTContext, transcription_prefs: Optional[dict] = None
    ) -> BatchTranscriptionResult:
        route = self.selector.select_finalize(context, transcription_prefs)
        return await self._transcribe('url', audio_url, context, route)

    async def transcribe_bytes(
        self, audio_bytes: bytes, context: STTContext, transcription_prefs: Optional[dict] = None
    ) -> BatchTranscriptionResult:
        route = self.selector.select_finalize(context, transcription_prefs)
        return await self._transcribe('bytes', audio_bytes, context, route)

    async def _transcribe(self, mode: str, payload, context: STTContext, route) -> BatchTranscriptionResult:
        last_error = None
        for provider_name in route.candidates:
            provider = self.registry.get_batch(provider_name)
            if provider is None:
                logger.warning('Finalize STT provider not registered: %s', provider_name)
                continue

            try:
                if mode == 'url':
                    result = await provider.transcribe_url(payload, context)
                else:
                    result = await provider.transcribe_bytes(payload, context)

                processed_segments = await self.post_processing_pipeline.process(list(result.segments), context)
                logger.info(
                    'Finalize STT provider selected provider=%s source=%s language=%s',
                    provider.name,
                    route.source,
                    route.language,
                )
                return replace(result, segments=processed_segments)
            except Exception as exc:
                last_error = exc
                logger.warning('Finalize STT provider failed provider=%s error=%s', provider_name, exc)

        if last_error:
            raise RuntimeError(f'Could not finalize transcription with any provider: {last_error}') from last_error
        raise RuntimeError('Could not finalize transcription with any provider')
