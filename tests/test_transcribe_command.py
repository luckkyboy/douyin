import json

from click.testing import CliRunner

from dy_cli.main import cli


class _FakeWhisperClient:
    def __init__(self):
        self.calls = []
        self.language = "zh"

    def transcribe(self, audio_path):
        self.calls.append(audio_path)
        return {
            "text": "转写文本",
            "text_raw": "转写文本",
            "segments": [{"text": "转写文本", "start_time": 0, "end_time": 1000, "speaker_id": 0, "words": []}],
            "raw": {"text": "转写文本"},
            "language": "zh",
        }


def test_transcribe_single_file_creates_json(monkeypatch, tmp_path):
    video_path = tmp_path / "001_alpha.mp4"
    video_path.write_bytes(b"video")
    fake_asr = _FakeWhisperClient()

    def fake_extract(video_path_value, audio_path_value):
        with open(audio_path_value, "wb") as f:
            f.write(b"audio")

    monkeypatch.setattr("dy_cli.commands.transcribe.extract_audio", fake_extract)
    monkeypatch.setattr("dy_cli.commands.transcribe.WhisperWebserviceClient.from_config", lambda: fake_asr)

    result = CliRunner().invoke(cli, ["transcribe", str(video_path)])

    output_path = tmp_path / "001_alpha.json"
    assert result.exit_code == 0
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["source_file"] == "001_alpha.mp4"
    assert payload["text"] == "转写文本"
    assert payload["text_raw"] == "转写文本"
    assert fake_asr.calls
    assert not (tmp_path / "001_alpha.transcribe.mp3").exists()


def test_transcribe_uses_ffmpeg_friendly_temp_audio_suffix(monkeypatch, tmp_path):
    video_path = tmp_path / "001_alpha.mp4"
    video_path.write_bytes(b"video")
    fake_asr = _FakeWhisperClient()
    captured = {}

    def fake_extract(video_path_value, audio_path_value):
        captured["audio_path"] = audio_path_value
        with open(audio_path_value, "wb") as f:
            f.write(b"audio")

    monkeypatch.setattr("dy_cli.commands.transcribe.extract_audio", fake_extract)
    monkeypatch.setattr("dy_cli.commands.transcribe.WhisperWebserviceClient.from_config", lambda: fake_asr)

    result = CliRunner().invoke(cli, ["transcribe", str(video_path)])

    assert result.exit_code == 0
    assert captured["audio_path"].endswith(".transcribe.part.mp3")


def test_transcribe_single_file_delete_video_keeps_mp3_and_json(monkeypatch, tmp_path):
    video_path = tmp_path / "001_alpha.mp4"
    video_path.write_bytes(b"video")
    fake_asr = _FakeWhisperClient()

    def fake_extract(video_path_value, audio_path_value):
        with open(audio_path_value, "wb") as f:
            f.write(b"audio")

    monkeypatch.setattr("dy_cli.commands.transcribe.extract_audio", fake_extract)
    monkeypatch.setattr("dy_cli.commands.transcribe.WhisperWebserviceClient.from_config", lambda: fake_asr)

    result = CliRunner().invoke(cli, ["transcribe", str(video_path), "--delete-video"])

    assert result.exit_code == 0
    assert not video_path.exists()
    assert (tmp_path / "001_alpha.transcribe.mp3").exists()
    assert (tmp_path / "001_alpha.json").exists()


def test_transcribe_dir_skips_existing_json(monkeypatch, tmp_path):
    first = tmp_path / "001_alpha.mp4"
    second = tmp_path / "002_beta.mp4"
    first.write_bytes(b"video")
    second.write_bytes(b"video")
    (tmp_path / "001_alpha.json").write_text("{}", encoding="utf-8")
    fake_asr = _FakeWhisperClient()

    def fake_extract(video_path_value, audio_path_value):
        with open(audio_path_value, "wb") as f:
            f.write(b"audio")

    monkeypatch.setattr("dy_cli.commands.transcribe.extract_audio", fake_extract)
    monkeypatch.setattr("dy_cli.commands.transcribe.WhisperWebserviceClient.from_config", lambda: fake_asr)

    result = CliRunner().invoke(cli, ["transcribe", str(tmp_path)])

    assert result.exit_code == 0
    assert len(fake_asr.calls) == 1
    assert (tmp_path / "002_beta.json").exists()


def test_transcribe_dir_writes_progress_and_resumes(monkeypatch, tmp_path):
    first = tmp_path / "001_alpha.mp4"
    second = tmp_path / "002_beta.mp4"
    first.write_bytes(b"video")
    second.write_bytes(b"video")
    (tmp_path / "001_alpha.json").write_text("{}", encoding="utf-8")
    (tmp_path / "transcribe_progress.json").write_text(
        json.dumps(
            {
                "version": 1,
                "root_dir": str(tmp_path),
                "total": 2,
                "completed": 1,
                "last_index": 1,
                "last_file": "001_alpha.mp4",
                "updated_at": "",
                "items": {
                    "001_alpha.mp4": {"status": "done", "output_json": "001_alpha.json"},
                    "002_beta.mp4": {"status": "failed", "output_json": "002_beta.json", "error": "timeout"},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    fake_asr = _FakeWhisperClient()

    def fake_extract(video_path_value, audio_path_value):
        with open(audio_path_value, "wb") as f:
            f.write(b"audio")

    monkeypatch.setattr("dy_cli.commands.transcribe.extract_audio", fake_extract)
    monkeypatch.setattr("dy_cli.commands.transcribe.WhisperWebserviceClient.from_config", lambda: fake_asr)

    result = CliRunner().invoke(cli, ["transcribe", str(tmp_path)])

    progress = json.loads((tmp_path / "transcribe_progress.json").read_text(encoding="utf-8"))
    assert result.exit_code == 0
    assert len(fake_asr.calls) == 1
    assert progress["completed"] == 2
    assert progress["last_file"] == "002_beta.mp4"
    assert progress["items"]["002_beta.mp4"]["status"] == "done"


def test_transcribe_help_registered_in_cli():
    result = CliRunner().invoke(cli, ["transcribe", "--help"])

    assert result.exit_code == 0
    assert "转写本地视频" in result.output
