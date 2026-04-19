import pytest

from dy_cli.services.asr import create_asr_client


def test_create_asr_client_defaults_to_whisper(monkeypatch):
    fake_client = object()
    monkeypatch.setattr("dy_cli.services.asr.config.get", lambda key, default=None: "whisper_webservice")
    monkeypatch.setattr("dy_cli.services.asr.WhisperWebserviceClient.from_config", lambda: fake_client)

    client = create_asr_client()

    assert client is fake_client


def test_create_asr_client_supports_tencent(monkeypatch):
    fake_client = object()
    monkeypatch.setattr("dy_cli.services.asr.config.get", lambda key, default=None: "tencent_asr")
    monkeypatch.setattr("dy_cli.services.asr.TencentAsrClient.from_config", lambda: fake_client)

    client = create_asr_client()

    assert client is fake_client


def test_create_asr_client_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr("dy_cli.services.asr.config.get", lambda key, default=None: "unknown")

    with pytest.raises(ValueError):
        create_asr_client()
