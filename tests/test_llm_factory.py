import pytest

from app.checker.llm_client import (
    DEFAULT_PROVIDER,
    PROVIDERS,
    DeepSeekClient,
    GrokClient,
    LLMConfigError,
    create_client,
    get_provider_spec,
    is_provider_configured,
    list_providers,
)


def test_providers_contains_deepseek_and_grok():
    assert set(PROVIDERS.keys()) == {'deepseek', 'grok'}
    assert PROVIDERS['deepseek'].cls is DeepSeekClient
    assert PROVIDERS['grok'].cls is GrokClient


def test_default_provider_is_known():
    assert DEFAULT_PROVIDER in PROVIDERS


def test_get_provider_spec_unknown_raises():
    with pytest.raises(LLMConfigError):
        get_provider_spec('mistral')


def test_get_provider_spec_empty_falls_back_to_default():
    assert get_provider_spec(None).key == DEFAULT_PROVIDER
    assert get_provider_spec('').key == DEFAULT_PROVIDER


def test_is_provider_configured_reads_config_first(monkeypatch):
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    assert is_provider_configured('deepseek', {'DEEPSEEK_API_KEY': 'x'})
    assert not is_provider_configured('deepseek', {'DEEPSEEK_API_KEY': ''})


def test_is_provider_configured_falls_back_to_env(monkeypatch):
    monkeypatch.setenv('GROK_API_KEY', 'xai-from-env')
    assert is_provider_configured('grok', {})


def test_create_client_uses_config_model_override():
    config = {'GROK_API_KEY': 'sk-test', 'GROK_MODEL': 'grok-3-mini'}
    client = create_client('grok', config)
    assert isinstance(client, GrokClient)
    assert client.model == 'grok-3-mini'


def test_create_client_falls_back_to_default_model():
    client = create_client('deepseek', {'DEEPSEEK_API_KEY': 'sk-test'})
    assert isinstance(client, DeepSeekClient)
    assert client.model == DeepSeekClient.DEFAULT_MODEL


def test_create_client_without_api_key_raises(monkeypatch):
    monkeypatch.delenv('GROK_API_KEY', raising=False)
    with pytest.raises(LLMConfigError):
        create_client('grok', {})


def test_list_providers_reports_configuration_flags(monkeypatch):
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    monkeypatch.delenv('GROK_API_KEY', raising=False)
    items = list_providers({'DEEPSEEK_API_KEY': 'x'})
    by_key = {item['key']: item for item in items}
    assert by_key['deepseek']['configured'] is True
    assert by_key['grok']['configured'] is False
    assert by_key['deepseek']['label'] == 'DeepSeek'
    assert by_key['grok']['label'] == 'Grok'
