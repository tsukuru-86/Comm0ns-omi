from typing import Dict, List, Optional

from utils.stt.contracts import BatchSTTProvider, StreamingSTTProvider
from utils.stt.providers import (
    DeepgramBatchProvider,
    DeepgramStreamingProvider,
    WhisperBatchProvider,
    WhisperStreamingProvider,
)


class ProviderRegistry:
    def __init__(self):
        self._streaming: Dict[str, StreamingSTTProvider] = {}
        self._batch: Dict[str, BatchSTTProvider] = {}

    def register_streaming(self, provider: StreamingSTTProvider) -> None:
        self._register(self._streaming, provider.name, provider)
        for alias in provider.aliases:
            self._register(self._streaming, alias, provider)

    def register_batch(self, provider: BatchSTTProvider) -> None:
        self._register(self._batch, provider.name, provider)
        for alias in provider.aliases:
            self._register(self._batch, alias, provider)

    def get_streaming(self, name: Optional[str]) -> Optional[StreamingSTTProvider]:
        if not name:
            return None
        return self._streaming.get(name)

    def get_batch(self, name: Optional[str]) -> Optional[BatchSTTProvider]:
        if not name:
            return None
        return self._batch.get(name)

    def list_streaming(self) -> List[str]:
        return sorted({provider.name for provider in self._streaming.values()})

    def list_batch(self) -> List[str]:
        return sorted({provider.name for provider in self._batch.values()})

    @staticmethod
    def _register(registry: dict, name: str, provider) -> None:
        if name in registry and registry[name] is not provider:
            raise ValueError(f'Provider name conflict: {name}')
        registry[name] = provider


_DEFAULT_PROVIDER_REGISTRY: Optional[ProviderRegistry] = None


def build_default_provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register_streaming(DeepgramStreamingProvider())
    registry.register_streaming(WhisperStreamingProvider())
    registry.register_batch(DeepgramBatchProvider())
    registry.register_batch(WhisperBatchProvider())
    return registry


def get_default_provider_registry() -> ProviderRegistry:
    global _DEFAULT_PROVIDER_REGISTRY
    if _DEFAULT_PROVIDER_REGISTRY is None:
        _DEFAULT_PROVIDER_REGISTRY = build_default_provider_registry()
    return _DEFAULT_PROVIDER_REGISTRY
