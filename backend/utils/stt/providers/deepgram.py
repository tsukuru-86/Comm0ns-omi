import asyncio
from typing import Callable, List, Optional, Sequence

from models.transcript_segment import TranscriptSegment
from utils.stt.contracts import (
    BatchSTTProvider,
    BatchTranscriptionResult,
    ProviderCapabilities,
    STTContext,
    STTEvent,
    STTEventType,
    StreamingSTTProvider,
)
from utils.stt.pre_recorded import (
    deepgram_prerecorded,
    deepgram_prerecorded_from_bytes,
    get_deepgram_model_for_language,
    postprocess_words,
)
from utils.stt.streaming import get_stt_service_for_language, process_audio_dg


class DeepgramStreamingProvider(StreamingSTTProvider):
    name = 'deepgram_streaming'
    aliases = ('deepgram',)
    capabilities = ProviderCapabilities(
        supports_streaming=True,
        supports_partial_results=False,
        supports_word_timestamps=True,
        supports_diarization=True,
        supports_confidence=False,
        supports_language_hint=True,
        supports_vocab_biasing=True,
        supports_endpointing=True,
    )

    async def open_stream(
        self,
        context: STTContext,
        sink: Callable[[STTEvent], None],
        vad_gate=None,
        is_active: Optional[Callable[[], bool]] = None,
    ):
        _, resolved_language, resolved_model = get_stt_service_for_language(
            context.language,
            multi_lang_enabled=context.multi_language_enabled,
        )

        def on_segments(segments: Sequence[dict]):
            annotated_segments: List[dict] = []
            for segment in segments:
                annotated = dict(segment)
                annotated['stt_provider'] = self.name
                annotated_segments.append(annotated)
            sink(
                STTEvent(
                    provider=self.name,
                    event_type=STTEventType.final,
                    segments=annotated_segments,
                    is_final=True,
                    metadata={'language': resolved_language, 'model': resolved_model},
                )
            )

        return await process_audio_dg(
            on_segments,
            resolved_language,
            context.sample_rate,
            context.channels,
            model=resolved_model,
            keywords=list(context.vocabulary),
            vad_gate=vad_gate,
            is_active=is_active,
        )


class DeepgramBatchProvider(BatchSTTProvider):
    name = 'deepgram_batch'
    aliases = ('deepgram_prerecorded',)
    capabilities = ProviderCapabilities(
        supports_streaming=False,
        supports_partial_results=False,
        supports_word_timestamps=True,
        supports_diarization=True,
        supports_confidence=False,
        supports_language_hint=True,
        supports_vocab_biasing=True,
        supports_endpointing=False,
    )

    async def transcribe_url(self, audio_url: str, context: STTContext) -> BatchTranscriptionResult:
        resolved_language, resolved_model = get_deepgram_model_for_language(context.language)
        words, detected_language = await asyncio.to_thread(
            deepgram_prerecorded,
            audio_url,
            None,
            0,
            True,
            True,
            resolved_language,
            resolved_model,
            list(context.vocabulary)[:100],
        )
        segments = self._build_segments(words)
        return BatchTranscriptionResult(
            provider=self.name,
            language=detected_language or resolved_language,
            segments=segments,
            raw_words=words,
            metadata={'model': resolved_model},
        )

    async def transcribe_bytes(self, audio_bytes: bytes, context: STTContext) -> BatchTranscriptionResult:
        resolved_language, resolved_model = get_deepgram_model_for_language(context.language)
        words, detected_language = await asyncio.to_thread(
            deepgram_prerecorded_from_bytes,
            audio_bytes,
            context.sample_rate,
            True,
            0,
            None,
            context.channels,
            resolved_language,
            resolved_model,
            True,
        )
        segments = self._build_segments(words)
        return BatchTranscriptionResult(
            provider=self.name,
            language=detected_language or resolved_language,
            segments=segments,
            raw_words=words,
            metadata={'model': resolved_model},
        )

    def _build_segments(self, words: Sequence[dict]) -> Sequence[TranscriptSegment]:
        segments = postprocess_words(list(words), duration=0)
        for segment in segments:
            segment.stt_provider = self.name
        return segments
