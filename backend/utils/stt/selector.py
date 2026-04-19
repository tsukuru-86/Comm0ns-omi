from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from utils.stt.config import STTConfiguration, load_stt_configuration, normalize_language_tag
from utils.stt.contracts import STTContext


@dataclass(frozen=True)
class ProviderRoute:
    phase: str
    primary: str
    candidates: Sequence[str]
    source: str
    language: str


class ProviderSelector:
    def __init__(self, registry=None):
        self.registry = registry

    def select_realtime(self, context: STTContext, transcription_prefs: Optional[dict] = None) -> ProviderRoute:
        return self._select_for_phase('realtime', context, transcription_prefs)

    def select_finalize(self, context: STTContext, transcription_prefs: Optional[dict] = None) -> ProviderRoute:
        return self._select_for_phase('finalize', context, transcription_prefs)

    def _select_for_phase(
        self,
        phase: str,
        context: STTContext,
        transcription_prefs: Optional[dict] = None,
    ) -> ProviderRoute:
        config = load_stt_configuration(transcription_prefs)
        prefs = transcription_prefs or {}
        provider_preferences = prefs.get('provider_preferences', {}) or {}

        normalized_language = normalize_language_tag(context.language)
        language_override = self._resolve_language_override(config.language_provider_overrides, normalized_language, phase)
        user_language_override = self._resolve_language_override(
            provider_preferences.get('language_overrides', {}) or {},
            normalized_language,
            phase,
            normalize_values=False,
        )

        explicit_provider = self._normalize_phase_provider(context.provider_hint, phase)
        user_provider = self._normalize_phase_provider(provider_preferences.get(phase), phase)
        user_language_provider = self._normalize_phase_provider(user_language_override, phase)
        env_language_provider = self._normalize_phase_provider(language_override, phase)
        default_provider = (
            config.default_realtime_provider if phase == 'realtime' else config.default_finalize_provider
        )

        if explicit_provider:
            primary = explicit_provider
            source = 'request'
        elif user_provider:
            primary = user_provider
            source = 'user'
        elif user_language_provider:
            primary = user_language_provider
            source = 'user_language'
        elif env_language_provider:
            primary = env_language_provider
            source = 'language'
        else:
            primary = default_provider
            source = 'default'

        fallbacks = self._resolve_fallbacks(config, provider_preferences, phase)
        if default_provider and default_provider != primary:
            fallbacks = self._dedupe(list(fallbacks) + [default_provider])
        candidates = self._dedupe([primary] + fallbacks)
        return ProviderRoute(
            phase=phase,
            primary=primary,
            candidates=candidates,
            source=source,
            language=normalized_language,
        )

    @staticmethod
    def _resolve_language_override(
        overrides: Dict[str, Dict[str, str]],
        language: str,
        phase: str,
        normalize_values: bool = True,
    ) -> Optional[str]:
        normalized_language = normalize_language_tag(language)
        base_language = normalized_language.split('-', 1)[0]
        for key in (normalized_language, base_language):
            override = overrides.get(key)
            if not isinstance(override, dict):
                continue
            value = override.get(phase)
            if value:
                if normalize_values:
                    return ProviderSelector._normalize_phase_provider(value, phase)
                return value
        return None

    @staticmethod
    def _resolve_fallbacks(config: STTConfiguration, provider_preferences: dict, phase: str) -> List[str]:
        pref_fallbacks = provider_preferences.get('fallbacks', {}) or {}
        raw = pref_fallbacks.get(phase)
        if isinstance(raw, list):
            return [provider for provider in (ProviderSelector._normalize_phase_provider(p, phase) for p in raw) if provider]
        return list(config.provider_fallbacks.get(phase, []))

    @staticmethod
    def _normalize_phase_provider(value: Optional[str], phase: str) -> Optional[str]:
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

    @staticmethod
    def _dedupe(values: Sequence[str]) -> List[str]:
        seen = set()
        deduped: List[str] = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped
