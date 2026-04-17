import subprocess

import pytest


def test_extract_audio_builds_ffmpeg_command(monkeypatch, tmp_path):
    from dy_cli.services.media import extract_audio

    video_path = tmp_path / "input.mp4"
    audio_path = tmp_path / "output.mp3"
    video_path.write_bytes(b"video")
    calls = {}

    monkeypatch.setattr("dy_cli.services.media.shutil.which", lambda name: "/usr/bin/ffmpeg")

    def fake_run(cmd, check, capture_output, text):
        calls["cmd"] = cmd
        calls["check"] = check
        calls["capture_output"] = capture_output
        calls["text"] = text
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("dy_cli.services.media.subprocess.run", fake_run)

    extract_audio(str(video_path), str(audio_path))

    assert calls["cmd"][:4] == ["ffmpeg", "-y", "-i", str(video_path)]
    assert "-vn" in calls["cmd"]
    assert "-ac" in calls["cmd"] and "1" in calls["cmd"]
    assert "-ar" in calls["cmd"] and "16000" in calls["cmd"]
    assert calls["cmd"][-1] == str(audio_path)
    assert calls["check"] is True
    assert calls["capture_output"] is True
    assert calls["text"] is True


def test_extract_audio_raises_when_ffmpeg_missing(monkeypatch):
    from dy_cli.services.media import MediaError, extract_audio

    monkeypatch.setattr("dy_cli.services.media.shutil.which", lambda name: "")

    with pytest.raises(MediaError, match="ffmpeg is required"):
        extract_audio("input.mp4", "output.mp3")
