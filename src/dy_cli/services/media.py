"""Local media processing helpers."""
from __future__ import annotations

import shutil
import subprocess


class MediaError(Exception):
    """Raised when local media processing fails."""


def extract_audio(video_path: str, audio_path: str) -> None:
    """Extract mono 16k audio using ffmpeg."""
    if not shutil.which("ffmpeg"):
        raise MediaError("ffmpeg is required")

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000", audio_path],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise MediaError(f"ffmpeg failed: {e.stderr or e.stdout or e}") from e
