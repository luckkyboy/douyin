"""Tencent Cloud ASR flash client."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

import httpx

from dy_cli.utils import config


class TencentASRError(Exception):
    """Raised when Tencent ASR fails."""


class TencentASRFlashClient:
    """Small client for Tencent ASR flash recognition."""

    endpoint = "https://asr.cloud.tencent.com"

    def __init__(
        self,
        *,
        app_id: str,
        secret_id: str,
        secret_key: str,
        engine_type: str = "16k_zh",
        timeout: int = 120,
    ):
        self.app_id = str(app_id)
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.engine_type = engine_type
        self.timeout = timeout

    @classmethod
    def from_config(cls) -> "TencentASRFlashClient":
        cfg = config.load_config()["asr"]["tencent"]
        return cls(
            app_id=str(cfg.get("app_id", "")),
            secret_id=cfg.get("secret_id", ""),
            secret_key=cfg.get("secret_key", ""),
            engine_type=cfg.get("engine_type", "16k_zh"),
        )

    @staticmethod
    def build_authorization(app_id: str, secret_key: str, params: dict[str, str]) -> str:
        query = urlencode(sorted(params.items()))
        sign_source = f"POSTasr.cloud.tencent.com/asr/flash/v1/{app_id}?{query}"
        digest = hmac.new(secret_key.encode("utf-8"), sign_source.encode("utf-8"), hashlib.sha1).digest()
        return base64.b64encode(digest).decode("utf-8")

    def transcribe(self, audio_path: str) -> dict:
        if not self.app_id or not self.secret_id or not self.secret_key:
            raise TencentASRError("Tencent ASR credentials are not configured")

        voice_format = os.path.splitext(audio_path)[1].lstrip(".").lower() or "mp3"
        timestamp = str(int(time.time()))
        params = {
            "convert_num_mode": "1",
            "engine_type": self.engine_type,
            "filter_dirty": "0",
            "filter_modal": "0",
            "filter_punc": "0",
            "first_channel_only": "1",
            "secretid": self.secret_id,
            "speaker_diarization": "0",
            "timestamp": timestamp,
            "voice_format": voice_format,
            "word_info": "3",
        }
        authorization = self.build_authorization(self.app_id, self.secret_key, params)
        query = urlencode(sorted(params.items()))
        url = f"{self.endpoint}/asr/flash/v1/{self.app_id}?{query}"

        with open(audio_path, "rb") as f:
            content = f.read()

        response = httpx.post(
            url,
            content=content,
            headers={
                "Authorization": authorization,
                "Content-Type": "application/octet-stream",
            },
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise TencentASRError(f"Tencent ASR HTTP {response.status_code}")
        payload = response.json()

        if payload.get("code") != 0:
            raise TencentASRError(payload.get("message", "Tencent ASR request failed"))

        flash_result = payload.get("flash_result", [])
        text = "\n".join(item.get("text", "") for item in flash_result if item.get("text")).strip()
        segments = []
        for channel in flash_result:
            for sentence in channel.get("sentence_list", []):
                segments.append(
                    {
                        "text": sentence.get("text", ""),
                        "start_time": sentence.get("start_time", 0),
                        "end_time": sentence.get("end_time", 0),
                        "speaker_id": sentence.get("speaker_id", 0),
                        "words": [
                            {
                                "word": word.get("word", ""),
                                "start_time": word.get("start_time", 0),
                                "end_time": word.get("end_time", 0),
                            }
                            for word in sentence.get("word_list", [])
                        ],
                    }
                )

        return {"text": text, "segments": segments, "raw": payload}
