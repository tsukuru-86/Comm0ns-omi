from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Protocol, Sequence, Tuple

from models.transcript_segment import TranscriptSegment


class STTEventType(str, Enum):
    partial = 'partial'
    final = 'final'
    error = 'error'
    status = 'status'


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_streaming: bool
    supports_partial_results: bool
    supports_word_timestamps: bool
    supports_diarization: bool
    supports_confidence: bool
    supports_language_hint: bool
    supports_vocab_biasing: bool
    supports_endpointing: bool
    supports_multichannel: bool = False


@dataclass(frozen=True)
class STTContext:
    uid: str
    session_id: str
    language: str = 'en'
    sample_rate: int = 16000
    channels: int = 1
    vocabulary: Sequence[str] = field(default_factory=tuple)
    source: Optional[str] = None
    conversation_id: Optional[str] = None
    provider_hint: Optional[str] = None
    multi_language_enabled: bool = True
    terminology: Dict[str, str] = field(default_factory=dict)
    phase: str = 'realtime'
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class STTEvent:
    provider: str
    event_type: STTEventType
    segments: Sequence[dict] = field(default_factory=tuple)
    is_final: bool = True
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BatchTranscriptionResult:
    provider: str
    language: str
    segments: Sequence[TranscriptSegment] = field(default_factory=tuple)
    raw_words: Sequence[dict] = field(default_factory=tuple)
    metadata: Dict[str, str] = field(default_factory=dict)


class StreamingSTTSession(Protocol):
    def send(self, audio: bytes) -> None:
        ...

    def finish(self) -> None:
        ...

    @property
    def is_connection_dead(self) -> bool:
        ...

    @property
    def death_reason(self) -> Optional[str]:
        ...


class StreamingSTTProvider(ABC):
    name: str
    aliases: Sequence[str] = ()
    capabilities: ProviderCapabilities

    def matches_name(self, value: Optional[str]) -> bool:
        if not value:
            return False
        return value == self.name or value in self.aliases

    @abstractmethod
    async def open_stream(
        self,
        context: STTContext,
        sink: Callable[[STTEvent], None],
        vad_gate=None,
        is_active: Optional[Callable[[], bool]] = None,
    ) -> StreamingSTTSession:
        raise NotImplementedError


class BatchSTTProvider(ABC):
    name: str
    aliases: Sequence[str] = ()
    capabilities: ProviderCapabilities

    def matches_name(self, value: Optional[str]) -> bool:
        if not value:
            return False
        return value == self.name or value in self.aliases

    @abstractmethod
    async def transcribe_url(self, audio_url: str, context: STTContext) -> BatchTranscriptionResult:
        raise NotImplementedError

    @abstractmethod
    async def transcribe_bytes(self, audio_bytes: bytes, context: STTContext) -> BatchTranscriptionResult:
        raise NotImplementedError


class TranscriptAssembler(ABC):
    @abstractmethod
    def assemble(
        self,
        existing_segments: List[TranscriptSegment],
        new_segments: List[TranscriptSegment],
        delta_seconds: int = 0,
    ) -> Tuple[List[TranscriptSegment], List[TranscriptSegment], List[str]]:
        raise NotImplementedError


class TranscriptPostProcessor(ABC):
    name: str

    @abstractmethod
    def supports(self, context: STTContext) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def process(self, segments: List[TranscriptSegment], context: STTContext) -> List[TranscriptSegment]:
        raise NotImplementedError


class FinalizeTranscriptionService(ABC):
    @abstractmethod
    async def transcribe_url(
        self, audio_url: str, context: STTContext, transcription_prefs: Optional[dict] = None
    ) -> BatchTranscriptionResult:
        raise NotImplementedError

    @abstractmethod
    async def transcribe_bytes(
        self, audio_bytes: bytes, context: STTContext, transcription_prefs: Optional[dict] = None
    ) -> BatchTranscriptionResult:
        raise NotImplementedError
