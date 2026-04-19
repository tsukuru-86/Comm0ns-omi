import logging
from typing import Optional

from utils.stt.config import load_stt_configuration
from utils.stt.finalize import DefaultFinalizeTranscriptionService
from utils.stt.postprocess import TranscriptPostProcessingPipeline, build_default_post_processors
from utils.stt.registry import get_default_provider_registry
from utils.stt.selector import ProviderSelector

logger = logging.getLogger(__name__)


def build_finalize_service(transcription_prefs: Optional[dict] = None) -> DefaultFinalizeTranscriptionService:
    """Build a ready-to-use finalize transcription service with default registry, selector, and post-processing."""
    registry = get_default_provider_registry()
    selector = ProviderSelector(registry)
    config = load_stt_configuration(transcription_prefs)
    pipeline = TranscriptPostProcessingPipeline(build_default_post_processors(config.enable_japanese_postprocessors))
    return DefaultFinalizeTranscriptionService(registry, selector, pipeline)
