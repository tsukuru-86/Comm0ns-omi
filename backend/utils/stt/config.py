import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def normalize_language_tag(language: Optional[str]) -> str:
    if not language:
        return 'en'
    normalized = language.replace('_', '-').strip()
    if normalized == 'auto':
        normalized = 'multi'
    return normalized or 'en'


def _normalize_provider_name(value: Optional[str], phase: str) -> Optional[str]:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None

    legacy_aliases = {
        'realtime': {
            'deepgram': 'deepgram_streaming',
            'whisper': 'whisper_streaming',
        },
        'finalize': {
            'deepgram': 'deepgram_batch',
            'whisper': 'whisper_batch',
        },
    }
    return legacy_aliases.get(phase, {}).get(normalized, normalized)


def _normalize_override_map(raw: dict) -> Dict[str, Dict[str, str]]:
    normalized: Dict[str, Dict[str, str]] = {}
    for language, override in raw.items():
        if not isinstance(override, dict):
            continue
        normalized[normalize_language_tag(language)] = {
            phase: provider
            for phase, provider in {
                'realtime': _normalize_provider_name(override.get('realtime'), 'realtime'),
                'finalize': _normalize_provider_name(override.get('finalize'), 'finalize'),
            }.items()
            if provider
        }
    return normalized


def _normalize_fallback_map(raw: dict) -> Dict[str, List[str]]:
    normalized: Dict[str, List[str]] = {}
    for phase in ('realtime', 'finalize'):
        providers = raw.get(phase, [])
        if not isinstance(providers, list):
            continue
        normalized[phase] = [provider for provider in (_normalize_provider_name(p, phase) for p in providers) if provider]
    return normalized


def _parse_json_env(name: str, default):
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning('Invalid JSON in %s, ignoring value', name)
        return default


@dataclass(frozen=True)
class STTConfiguration:
    default_realtime_provider: str = 'deepgram_streaming'
    default_finalize_provider: str = 'deepgram_batch'
    language_provider_overrides: Dict[str, Dict[str, str]] = field(default_factory=dict)
    provider_fallbacks: Dict[str, List[str]] = field(default_factory=dict)
    enable_japanese_postprocessors: bool = True


def load_stt_configuration(transcription_prefs: Optional[dict] = None) -> STTConfiguration:
    transcription_prefs = transcription_prefs or {}
    provider_preferences = transcription_prefs.get('provider_preferences', {}) or {}

    env_language_overrides = _normalize_override_map(_parse_json_env('STT_LANGUAGE_PROVIDER_OVERRIDES', {}))
    env_fallbacks = _normalize_fallback_map(_parse_json_env('STT_PROVIDER_FALLBACK_CHAIN', {}))

    pref_language_overrides = _normalize_override_map(provider_preferences.get('language_overrides', {}) or {})
    pref_fallbacks = _normalize_fallback_map(provider_preferences.get('fallbacks', {}) or {})

    merged_language_overrides = dict(env_language_overrides)
    merged_language_overrides.update(pref_language_overrides)

    merged_fallbacks = dict(env_fallbacks)
    for phase, providers in pref_fallbacks.items():
        merged_fallbacks[phase] = providers

    default_realtime_provider = _normalize_provider_name(
        provider_preferences.get('realtime') or os.getenv('STT_DEFAULT_REALTIME_PROVIDER', 'deepgram_streaming'),
        'realtime',
    )
    default_finalize_provider = _normalize_provider_name(
        provider_preferences.get('finalize') or os.getenv('STT_DEFAULT_FINALIZE_PROVIDER', 'deepgram_batch'),
        'finalize',
    )

    enable_ja_postprocessors = provider_preferences.get(
        'enable_japanese_postprocessors',
        os.getenv('STT_ENABLE_JA_POSTPROCESSORS', 'true').lower() == 'true',
    )

    return STTConfiguration(
        default_realtime_provider=default_realtime_provider or 'deepgram_streaming',
        default_finalize_provider=default_finalize_provider or 'deepgram_batch',
        language_provider_overrides=merged_language_overrides,
        provider_fallbacks=merged_fallbacks,
        enable_japanese_postprocessors=bool(enable_ja_postprocessors),
    )
