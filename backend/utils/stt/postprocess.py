import re
from typing import Iterable, List, Optional, Sequence

from models.transcript_segment import TranscriptSegment
from utils.stt.config import normalize_language_tag
from utils.stt.contracts import STTContext, TranscriptPostProcessor


_JAPANESE_CHARACTER_RE = re.compile(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]')
_LEADING_JA_FILLER_RE = re.compile(r'^(えーと|えっと|あの|あのー|そのー|まー|まあ)\s+')


def _language_base(language: Optional[str]) -> str:
    return normalize_language_tag(language).split('-', 1)[0]


class TranscriptPostProcessingPipeline:
    def __init__(self, processors: Optional[Sequence[TranscriptPostProcessor]] = None):
        self.processors = list(processors or [])

    async def process(self, segments: List[TranscriptSegment], context: STTContext) -> List[TranscriptSegment]:
        current_segments = list(segments)
        for processor in self.processors:
            if not processor.supports(context):
                continue
            current_segments = await processor.process(current_segments, context)
        return current_segments


class JapanesePunctuationNormalizer(TranscriptPostProcessor):
    name = 'ja_punctuation_normalizer'

    def supports(self, context: STTContext) -> bool:
        return _language_base(context.language) == 'ja'

    async def process(self, segments: List[TranscriptSegment], context: STTContext) -> List[TranscriptSegment]:
        for segment in segments:
            text = segment.text.strip().replace('  ', ' ')
            text = text.replace(' 、', '、').replace(' 。', '。').replace(' ？', '？').replace(' ！', '！')
            if _JAPANESE_CHARACTER_RE.search(text):
                text = text.replace(',', '、').replace('.', '。')
            segment.text = text
        return segments


class JapaneseFillerCleanupProcessor(TranscriptPostProcessor):
    name = 'ja_filler_cleanup'

    def supports(self, context: STTContext) -> bool:
        return (
            _language_base(context.language) == 'ja'
            and context.metadata.get('enable_ja_filler_cleanup', 'false').lower() == 'true'
        )

    async def process(self, segments: List[TranscriptSegment], context: STTContext) -> List[TranscriptSegment]:
        for segment in segments:
            segment.text = _LEADING_JA_FILLER_RE.sub('', segment.text.strip())
        return segments


class TerminologyCorrectionProcessor(TranscriptPostProcessor):
    name = 'terminology_correction'

    def supports(self, context: STTContext) -> bool:
        return bool(context.terminology)

    async def process(self, segments: List[TranscriptSegment], context: STTContext) -> List[TranscriptSegment]:
        replacements = sorted(context.terminology.items(), key=lambda item: len(item[0]), reverse=True)
        for segment in segments:
            updated = segment.text
            for source, target in replacements:
                if source:
                    updated = updated.replace(source, target)
            segment.text = updated
        return segments


def build_default_post_processors(enable_japanese_postprocessors: bool = True) -> Iterable[TranscriptPostProcessor]:
    processors: List[TranscriptPostProcessor] = [TerminologyCorrectionProcessor()]
    if enable_japanese_postprocessors:
        processors.insert(0, JapanesePunctuationNormalizer())
        processors.insert(1, JapaneseFillerCleanupProcessor())
    return processors
