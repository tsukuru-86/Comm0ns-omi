from importlib import import_module

_EXPORTS = {
    'BatchSTTProvider': ('utils.stt.contracts', 'BatchSTTProvider'),
    'BatchTranscriptionResult': ('utils.stt.contracts', 'BatchTranscriptionResult'),
    'FinalizeTranscriptionService': ('utils.stt.contracts', 'FinalizeTranscriptionService'),
    'ProviderCapabilities': ('utils.stt.contracts', 'ProviderCapabilities'),
    'STTContext': ('utils.stt.contracts', 'STTContext'),
    'STTEvent': ('utils.stt.contracts', 'STTEvent'),
    'STTEventType': ('utils.stt.contracts', 'STTEventType'),
    'StreamingSTTProvider': ('utils.stt.contracts', 'StreamingSTTProvider'),
    'StreamingSTTSession': ('utils.stt.contracts', 'StreamingSTTSession'),
    'TranscriptAssembler': ('utils.stt.contracts', 'TranscriptAssembler'),
    'TranscriptPostProcessor': ('utils.stt.contracts', 'TranscriptPostProcessor'),
    'ProviderRegistry': ('utils.stt.registry', 'ProviderRegistry'),
    'build_default_provider_registry': ('utils.stt.registry', 'build_default_provider_registry'),
    'get_default_provider_registry': ('utils.stt.registry', 'get_default_provider_registry'),
    'ProviderRoute': ('utils.stt.selector', 'ProviderRoute'),
    'ProviderSelector': ('utils.stt.selector', 'ProviderSelector'),
    'RealtimeProviderHandle': ('utils.stt.runtime', 'RealtimeProviderHandle'),
    'open_realtime_stt_session': ('utils.stt.runtime', 'open_realtime_stt_session'),
    'DefaultFinalizeTranscriptionService': ('utils.stt.finalize', 'DefaultFinalizeTranscriptionService'),
    'STTConfiguration': ('utils.stt.config', 'STTConfiguration'),
    'load_stt_configuration': ('utils.stt.config', 'load_stt_configuration'),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')

    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
