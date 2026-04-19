import json

import pytest

from dy_cli.services.tencent_asr import TencentAsrClient, TencentAsrError


class _FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload or {}
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


def test_tencent_asr_transcribe_polls_until_success(monkeypatch, tmp_path):
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"audio")
    captured = []
    responses = [
        _FakeResponse(payload={"Response": {"RequestId": "req-1", "Data": {"TaskId": 42}}}),
        _FakeResponse(payload={"Response": {"RequestId": "req-2", "Data": {"Status": 1, "StatusStr": "doing"}}}),
        _FakeResponse(
            payload={
                "Response": {
                    "RequestId": "req-3",
                    "Data": {
                        "TaskId": 42,
                        "Status": 2,
                        "StatusStr": "success",
                        "Result": "[0:0.000,0:1.000] 龙非说话",
                        "ResultDetail": [
                            {
                                "FinalSentence": "龙非说话",
                                "StartMs": 0,
                                "EndMs": 1000,
                                "SpeakerId": 0,
                                "Words": [
                                    {"Word": "龙非", "OffsetStartMs": 0, "OffsetEndMs": 500},
                                    {"Word": "说话", "OffsetStartMs": 500, "OffsetEndMs": 1000},
                                ],
                            }
                        ],
                    },
                }
            }
        ),
    ]

    def fake_post(url, *, content, headers, timeout):
        captured.append(
            {
                "url": url,
                "payload": json.loads(content.decode("utf-8")),
                "headers": headers,
                "timeout": timeout,
            }
        )
        return responses.pop(0)

    monkeypatch.setattr("dy_cli.services.tencent_asr.httpx.post", fake_post)
    monkeypatch.setattr("dy_cli.services.tencent_asr.time.sleep", lambda _: None)

    client = TencentAsrClient(
        secret_id="sid",
        secret_key="skey",
        region="ap-shanghai",
        replace_map={"龙非": "龙飞"},
        poll_interval_seconds=1,
        max_wait_seconds=10,
    )
    result = client.transcribe(str(audio_path))

    assert captured[0]["headers"]["X-TC-Action"] == "CreateRecTask"
    assert captured[0]["payload"]["SourceType"] == 1
    assert captured[1]["headers"]["X-TC-Action"] == "DescribeTaskStatus"
    assert captured[1]["payload"] == {"TaskId": 42}
    assert result["engine"] == "tencent_asr"
    assert result["language"] == "zh"
    assert result["text_raw"] == "龙非说话"
    assert result["text"] == "龙飞说话"
    assert result["segments"][0]["text"] == "龙飞说话"
    assert result["segments"][0]["words"][0]["text"] == "龙飞"


def test_tencent_asr_rejects_large_inline_audio(tmp_path):
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"a" * (TencentAsrClient.max_inline_audio_bytes + 1))
    client = TencentAsrClient(secret_id="sid", secret_key="skey")

    with pytest.raises(TencentAsrError):
        client.transcribe(str(audio_path))


def test_tencent_asr_from_config_parses_string_replace_map(monkeypatch):
    monkeypatch.setattr(
        "dy_cli.services.tencent_asr.config.load_config",
        lambda: {
            "asr": {
                "tencent": {
                    "secret_id": "sid",
                    "secret_key": "skey",
                },
                "replace_map": '{"龙非":"龙飞"}',
                "tencent_asr": {
                    "region": "ap-shanghai",
                    "engine_model_type": "16k_zh",
                    "channel_num": 1,
                    "res_text_format": 3,
                    "convert_num_mode": 1,
                    "speaker_diarization": 0,
                    "poll_interval_seconds": 5,
                    "max_wait_seconds": 1800,
                    "timeout": 60,
                },
            }
        },
    )

    client = TencentAsrClient.from_config()

    assert client.replace_map == {"龙非": "龙飞"}
    assert client.secret_id == "sid"
