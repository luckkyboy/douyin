import json

import pytest

from dy_cli.services.whisper_webservice import WhisperWebserviceClient, WhisperWebserviceError


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_transcribe_posts_audio_with_expected_params(monkeypatch, tmp_path):
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"audio")
    captured = {}

    def fake_post(url, *, files, params, timeout):
        captured["url"] = url
        captured["files"] = files
        captured["params"] = params
        captured["timeout"] = timeout
        return _FakeResponse(
            payload={
                "text": "龙非说话",
                "segments": [{"text": "龙非说话", "start": 0.0, "end": 1.0}],
                "language": "zh",
            }
        )

    monkeypatch.setattr("dy_cli.services.whisper_webservice.httpx.post", fake_post)

    client = WhisperWebserviceClient(
        base_url="http://127.0.0.1:9000",
        language="zh",
        vad_filter=True,
        word_timestamps=False,
        replace_map={"龙非": "龙飞"},
    )
    result = client.transcribe(str(audio_path))

    assert captured["url"] == "http://127.0.0.1:9000/asr"
    assert captured["params"]["output"] == "json"
    assert captured["params"]["task"] == "transcribe"
    assert captured["params"]["language"] == "zh"
    assert captured["params"]["vad_filter"] == "true"
    assert captured["params"]["word_timestamps"] == "false"
    assert captured["files"]["audio_file"][0] == "sample.mp3"
    assert result["text_raw"] == "龙非说话"
    assert result["text"] == "龙飞说话"
    assert result["language"] == "zh"


def test_transcribe_raises_on_http_error(monkeypatch, tmp_path):
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"audio")

    def fake_post(url, *, files, params, timeout):
        return _FakeResponse(status_code=500, text="boom")

    monkeypatch.setattr("dy_cli.services.whisper_webservice.httpx.post", fake_post)

    client = WhisperWebserviceClient(base_url="http://127.0.0.1:9000")

    with pytest.raises(WhisperWebserviceError):
        client.transcribe(str(audio_path))


def test_from_config_parses_string_replace_map(monkeypatch):
    monkeypatch.setattr(
        "dy_cli.services.whisper_webservice.config.load_config",
        lambda: {
            "asr": {
                "replace_map": '{"龙非":"龙飞"}',
                "whisper_webservice": {
                    "base_url": "http://127.0.0.1:9000",
                    "language": "zh",
                    "task": "transcribe",
                    "vad_filter": True,
                    "word_timestamps": False,
                    "encode": True,
                    "timeout": 600,
                    "initial_prompt": "",
                },
            }
        },
    )

    client = WhisperWebserviceClient.from_config()

    assert client.replace_map == {"龙非": "龙飞"}
