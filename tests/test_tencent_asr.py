import base64
import hashlib
import hmac
import httpx
import pytest

from dy_cli.services.tencent_asr import TencentASRError, TencentASRFlashClient


def test_build_authorization_uses_documented_hmac_sha1_formula():
    params = {
        "engine_type": "16k_zh_beta",
        "extra_punc": "0",
        "filter_punc": "0",
        "first_channel_only": "1",
        "hotword_id": "584f4d0060d811ed85da525400aec391",
        "reinforce_hotword": "0",
        "secretid": "*****Qq1zhZMN8dv0******",
        "speaker_diarization": "0",
        "timestamp": "1673426168",
        "voice_format": "wav",
        "word_info": "1",
    }

    app_id = "125922123"
    secret_key = "secret-key-demo"
    signature = TencentASRFlashClient.build_authorization(app_id=app_id, secret_key=secret_key, params=params)
    sign_source = (
        "POSTasr.cloud.tencent.com/asr/flash/v1/125922123"
        "?engine_type=16k_zh_beta&extra_punc=0&filter_punc=0&first_channel_only=1"
        "&hotword_id=584f4d0060d811ed85da525400aec391&reinforce_hotword=0"
        "&secretid=%2A%2A%2A%2A%2AQq1zhZMN8dv0%2A%2A%2A%2A%2A%2A"
        "&speaker_diarization=0&timestamp=1673426168&voice_format=wav&word_info=1"
    )
    expected = base64.b64encode(
        hmac.new(secret_key.encode("utf-8"), sign_source.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")

    assert signature == expected


def test_transcribe_audio_returns_text_and_raw_response(monkeypatch, tmp_path):
    audio_path = tmp_path / "input.mp3"
    audio_path.write_bytes(b"audio")
    client = TencentASRFlashClient(
        app_id="10000",
        secret_id="secret-id",
        secret_key="secret-key",
        engine_type="16k_zh",
    )

    monkeypatch.setattr("dy_cli.services.tencent_asr.time.time", lambda: 1700000000)

    response_payload = {
        "code": 0,
        "message": "",
        "request_id": "req-1",
        "audio_duration": 2386,
        "flash_result": [
            {
                "channel_id": 0,
                "text": "腾讯云智能语音欢迎您。",
                "sentence_list": [
                    {
                        "text": "腾讯云智能语音欢迎您。",
                        "start_time": 0,
                        "end_time": 2386,
                        "speaker_id": 0,
                        "word_list": [
                            {"word": "腾讯云", "start_time": 0, "end_time": 780},
                            {"word": "智能语音", "start_time": 780, "end_time": 1590},
                        ],
                    }
                ],
            }
        ],
    }

    captured = {}

    def fake_post(url, *, content, headers, timeout):
        captured["url"] = url
        captured["content"] = content
        captured["headers"] = headers
        captured["timeout"] = timeout
        return httpx.Response(200, json=response_payload, request=httpx.Request("POST", url))

    monkeypatch.setattr("dy_cli.services.tencent_asr.httpx.post", fake_post)

    result = client.transcribe(str(audio_path))

    assert "engine_type=16k_zh" in captured["url"]
    assert "voice_format=mp3" in captured["url"]
    assert captured["content"] == b"audio"
    assert captured["headers"]["Authorization"]
    assert result["text"] == "腾讯云智能语音欢迎您。"
    assert result["segments"] == [
        {
            "text": "腾讯云智能语音欢迎您。",
            "start_time": 0,
            "end_time": 2386,
            "speaker_id": 0,
            "words": [
                {"word": "腾讯云", "start_time": 0, "end_time": 780},
                {"word": "智能语音", "start_time": 780, "end_time": 1590},
            ],
        }
    ]
    assert result["raw"] == response_payload


def test_transcribe_audio_raises_on_non_zero_code(monkeypatch, tmp_path):
    audio_path = tmp_path / "input.mp3"
    audio_path.write_bytes(b"audio")
    client = TencentASRFlashClient(
        app_id="10000",
        secret_id="secret-id",
        secret_key="secret-key",
        engine_type="16k_zh",
    )

    monkeypatch.setattr("dy_cli.services.tencent_asr.time.time", lambda: 1700000000)

    def fake_post(url, *, content, headers, timeout):
        return httpx.Response(
            200,
            json={"code": 4002, "message": "鉴权失败", "request_id": "req-2"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("dy_cli.services.tencent_asr.httpx.post", fake_post)

    with pytest.raises(TencentASRError, match="鉴权失败"):
        client.transcribe(str(audio_path))
