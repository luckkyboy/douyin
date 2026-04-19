import base64
import hashlib
import hmac
import json

import pytest

from dy_cli.services.tencent_flash_asr import TencentFlashAsrClient, TencentFlashAsrError


class _FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload or {}
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


def test_tencent_flash_asr_posts_audio_with_expected_signature(monkeypatch, tmp_path):
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"audio")
    captured = {}
    monkeypatch.setattr("dy_cli.services.tencent_flash_asr.time.time", lambda: 1700000000)

    def fake_post(url, *, content, headers, timeout):
        captured["url"] = url
        captured["content"] = content
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _FakeResponse(
            payload={
                "code": 0,
                "message": "",
                "request_id": "req-1",
                "audio_duration": 1000,
                "flash_result": [
                    {
                        "channel_id": 0,
                        "text": "龙非说话。",
                        "sentence_list": [
                            {
                                "text": "龙非说话。",
                                "start_time": 0,
                                "end_time": 1000,
                                "speaker_id": 0,
                                "word_list": [
                                    {"word": "龙非", "start_time": 0, "end_time": 400},
                                    {"word": "说话", "start_time": 400, "end_time": 900},
                                ],
                            }
                        ],
                    }
                ],
            }
        )

    monkeypatch.setattr("dy_cli.services.tencent_flash_asr.httpx.post", fake_post)

    client = TencentFlashAsrClient(
        app_id="12345",
        secret_id="sid",
        secret_key="skey",
        engine_type="16k_zh",
        word_info=1,
        replace_map={"龙非": "龙飞"},
    )
    result = client.transcribe(str(audio_path))

    expected_query = (
        "convert_num_mode=1&engine_type=16k_zh&filter_dirty=0&filter_modal=0&filter_punc=0"
        "&first_channel_only=1&secretid=sid&speaker_diarization=0&timestamp=1700000000&voice_format=mp3&word_info=1"
    )
    expected_source = f"POSTasr.cloud.tencent.com/asr/flash/v1/12345?{expected_query}"
    expected_signature = base64.b64encode(
        hmac.new(b"skey", expected_source.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")

    assert captured["url"] == f"https://asr.cloud.tencent.com/asr/flash/v1/12345?{expected_query}"
    assert captured["headers"]["Authorization"] == expected_signature
    assert captured["headers"]["Content-Type"] == "application/octet-stream"
    assert captured["content"] == b"audio"
    assert result["engine"] == "tencent_flash_asr"
    assert result["text_raw"] == "龙非说话。"
    assert result["text"] == "龙飞说话。"
    assert result["segments"][0]["text"] == "龙飞说话。"
    assert result["segments"][0]["words"][0]["text"] == "龙飞"


def test_tencent_flash_asr_rejects_large_audio(tmp_path):
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"a" * (TencentFlashAsrClient.max_audio_bytes + 1))
    client = TencentFlashAsrClient(app_id="12345", secret_id="sid", secret_key="skey")

    with pytest.raises(TencentFlashAsrError):
        client.transcribe(str(audio_path))


def test_tencent_flash_asr_from_config_parses_string_replace_map(monkeypatch):
    monkeypatch.setattr(
        "dy_cli.services.tencent_flash_asr.config.load_config",
        lambda: {
            "asr": {
                "tencent": {
                    "app_id": "12345",
                    "secret_id": "sid",
                    "secret_key": "skey",
                },
                "replace_map": '{"龙非":"龙飞"}',
                "tencent_asr_flash": {
                    "engine_type": "16k_zh",
                    "speaker_diarization": 0,
                    "filter_dirty": 0,
                    "filter_modal": 0,
                    "filter_punc": 0,
                    "convert_num_mode": 1,
                    "word_info": 0,
                    "first_channel_only": 1,
                    "sentence_max_length": 0,
                    "hotword_id": "",
                    "customization_id": "",
                    "hotword_list": "",
                    "input_sample_rate": 0,
                    "timeout": 120,
                },
            }
        },
    )

    client = TencentFlashAsrClient.from_config()

    assert client.replace_map == {"龙非": "龙飞"}
    assert client.app_id == "12345"
    assert client.secret_id == "sid"
    assert client.engine_type == "16k_zh"
