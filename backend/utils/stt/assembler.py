from typing import List

from models.transcript_segment import TranscriptSegment
from utils.stt.contracts import TranscriptAssembler


class DefaultTranscriptAssembler(TranscriptAssembler):
    def assemble(
        self,
        existing_segments: List[TranscriptSegment],
        new_segments: List[TranscriptSegment],
        delta_seconds: int = 0,
    ):
        return TranscriptSegment.combine_segments(existing_segments, new_segments, delta_seconds=delta_seconds)
