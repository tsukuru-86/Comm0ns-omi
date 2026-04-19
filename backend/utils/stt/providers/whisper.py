import asyncio
import logging
import os
import tempfile
import uuid
from typing import Sequence

from models.transcript_segment import TranscriptSegment
from utils.stt.contracts import (
    BatchSTTProvider,
    BatchTranscriptionResult,
    ProviderCapabilities,
    STTContext,
    StreamingSTTProvider,
)
from utils.stt.pre_recorded import fal_whisperx, postprocess_words

logger = logging.getLogger(__name__)


class WhisperStreamingProvider(StreamingSTTProvider):
    name = 'whisper_streaming'
    aliases = ('faster_whisper_streaming',)
    capabilities = ProviderCapabilities(
        supports_streaming=True,
        supports_partial_results=True,
        supports_word_timestamps=True,
        supports_diarization=False,
        supports_confidence=False,
        supports_language_hint=True,
        supports_vocab_biasing=False,
        supports_endpointing=False,
    )

    async def open_stream(self, context: STTContext, sink, vad_gate=None, is_active=None):
        raise NotImplementedError(
            'Whisper streaming provider is a scaffold. Wire a hosted or local faster-whisper stream before enabling it.'
        )


class WhisperBatchProvider(BatchSTTProvider):
    name = 'whisper_batch'
    aliases = ('whisperx', 'fal_whisperx')
    capabilities = ProviderCapabilities(
        supports_streaming=False,
        supports_partial_results=False,
        supports_word_timestamps=True,
        supports_diarization=True,
        supports_confidence=False,
        supports_language_hint=False,
        supports_vocab_biasing=False,
        supports_endpointing=False,
    )

    async def transcribe_url(self, audio_url: str, context: STTContext) -> BatchTranscriptionResult:
        words, detected_language = await asyncio.to_thread(fal_whisperx, audio_url, None, 0, True, True, 'word')
        segments = self._build_segments(words)
        return BatchTranscriptionResult(
            provider=self.name,
            language=detected_language or context.language,
            segments=segments,
            raw_words=words,
            metadata={'implementation': 'fal_whisperx'},
        )

    async def transcribe_bytes(self, audio_bytes: bytes, context: STTContext) -> BatchTranscriptionResult:
        from utils.other.storage import upload_postprocessing_audio, delete_postprocessing_audio

        tmp_name = f'whisper_staging_{uuid.uuid4().hex}.wav'
        tmp_path = os.path.join(tempfile.gettempdir(), tmp_name)
        try:
            with open(tmp_path, 'wb') as f:
                f.write(audio_bytes)
            audio_url = await asyncio.to_thread(upload_postprocessing_audio, tmp_path)
            logger.info('Whisper batch bytes staged to %s', audio_url)
            result = await self.transcribe_url(audio_url, context)
            asyncio.get_event_loop().call_later(
                300, lambda: asyncio.ensure_future(asyncio.to_thread(delete_postprocessing_audio, tmp_path))
            )
            return result
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _build_segments(self, words: Sequence[dict]) -> Sequence[TranscriptSegment]:
        segments = postprocess_words(list(words), duration=0)
        for segment in segments:
            segment.stt_provider = self.name
        return segments
