"""Local Whisper ASR webservice client."""
from __future__ import annotations

import os
from copy import deepcopy

import httpx

from dy_cli.utils import config


class WhisperWebserviceError(Exception):
    """Raised when the local Whisper webservice fails."""


class WhisperWebserviceClient:
    """Client for onerahmet/openai-whisper-asr-webservice."""

    def __init__(
        self,
        *,
        base_url: str,
        language: str = "zh",
        task: str = "transcribe",
        vad_filter: bool = True,
        word_timestamps: bool = False,
        encode: bool = True,
        timeout: int = 600,
        initial_prompt: str = "",
        replace_map: dict[str, str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.language = language
        self.task = task
        self.vad_filter = vad_filter
        self.word_timestamps = word_timestamps
        self.encode = encode
        self.timeout = timeout
        self.initial_prompt = initial_prompt
        self.replace_map = dict(replace_map or {})

    @classmethod
    def from_config(cls) -> "WhisperWebserviceClient":
        cfg = config.load_config()["asr"]
        whisper_cfg = cfg.get("whisper_webservice", {})
        return cls(
            base_url=whisper_cfg.get("base_url", "http://127.0.0.1:9000"),
            language=whisper_cfg.get("language", "zh"),
            task=whisper_cfg.get("task", "transcribe"),
            vad_filter=bool(whisper_cfg.get("vad_filter", True)),
            word_timestamps=bool(whisper_cfg.get("word_timestamps", False)),
            encode=bool(whisper_cfg.get("encode", True)),
            timeout=int(whisper_cfg.get("timeout", 600)),
            initial_prompt=whisper_cfg.get("initial_prompt", ""),
            replace_map=cfg.get("replace_map", {}),
        )

    def transcribe(self, audio_path: str) -> dict:
        if not self.base_url:
            raise WhisperWebserviceError("Whisper webservice base URL is not configured")

        params = {
            "output": "json",
            "task": self.task,
            "language": self.language,
            "vad_filter": self._bool_param(self.vad_filter),
            "word_timestamps": self._bool_param(self.word_timestamps),
            "encode": self._bool_param(self.encode),
        }
        if self.initial_prompt:
            params["initial_prompt"] = self.initial_prompt

        try:
            with open(audio_path, "rb") as audio_file:
                response = httpx.post(
                    f"{self.base_url}/asr",
                    files={"audio_file": (os.path.basename(audio_path), audio_file)},
                    params=params,
                    timeout=self.timeout,
                )
        except OSError as e:
            raise WhisperWebserviceError(f"Failed to read audio file: {e}") from e
        except httpx.HTTPError as e:
            raise WhisperWebserviceError(f"Whisper webservice request failed: {e}") from e

        if response.status_code >= 400:
            detail = response.text.strip() or f"HTTP {response.status_code}"
            raise WhisperWebserviceError(f"Whisper webservice HTTP {response.status_code}: {detail}")

        try:
            payload = response.json()
        except ValueError as e:
            raise WhisperWebserviceError("Whisper webservice returned invalid JSON") from e

        if not isinstance(payload, dict):
            raise WhisperWebserviceError("Whisper webservice returned unexpected response")

        text_raw = str(payload.get("text", "") or "").strip()
        segments = self._apply_replace_map_to_value(payload.get("segments", []))

        return {
            "engine": "whisper_webservice",
            "language": payload.get("language") or self.language,
            "text_raw": text_raw,
            "text": self._apply_replace_map_to_text(text_raw),
            "segments": segments,
            "raw": payload,
        }

    @staticmethod
    def _bool_param(value: bool) -> str:
        return "true" if value else "false"

    def _apply_replace_map_to_text(self, text: str) -> str:
        corrected = text
        for source, target in self.replace_map.items():
            corrected = corrected.replace(source, target)
        return corrected

    def _apply_replace_map_to_value(self, value):
        if isinstance(value, str):
            return self._apply_replace_map_to_text(value)
        if isinstance(value, list):
            return [self._apply_replace_map_to_value(item) for item in value]
        if isinstance(value, dict):
            corrected = deepcopy(value)
            for key, item in corrected.items():
                corrected[key] = self._apply_replace_map_to_value(item)
            return corrected
        return value
