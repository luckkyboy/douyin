"""Tencent Cloud flash file ASR client."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from copy import deepcopy
from urllib.parse import urlencode

import httpx

from dy_cli.utils import config


class TencentFlashAsrError(Exception):
    """Raised when Tencent flash ASR fails."""


class TencentFlashAsrClient:
    """Client for Tencent Cloud flash file ASR."""

    endpoint = "https://asr.cloud.tencent.com"
    host = "asr.cloud.tencent.com"
    max_audio_bytes = 100 * 1024 * 1024

    def __init__(
        self,
        *,
        app_id: str,
        secret_id: str,
        secret_key: str,
        engine_type: str = "16k_zh",
        speaker_diarization: int = 0,
        filter_dirty: int = 0,
        filter_modal: int = 0,
        filter_punc: int = 0,
        convert_num_mode: int = 1,
        word_info: int = 0,
        first_channel_only: int = 1,
        sentence_max_length: int = 0,
        hotword_id: str = "",
        customization_id: str = "",
        hotword_list: str = "",
        input_sample_rate: int = 0,
        timeout: int = 120,
        replace_map: dict[str, str] | None = None,
    ):
        self.app_id = str(app_id).strip()
        self.secret_id = str(secret_id).strip()
        self.secret_key = str(secret_key).strip()
        self.engine_type = engine_type
        self.speaker_diarization = int(speaker_diarization)
        self.filter_dirty = int(filter_dirty)
        self.filter_modal = int(filter_modal)
        self.filter_punc = int(filter_punc)
        self.convert_num_mode = int(convert_num_mode)
        self.word_info = int(word_info)
        self.first_channel_only = int(first_channel_only)
        self.sentence_max_length = int(sentence_max_length)
        self.hotword_id = str(hotword_id).strip()
        self.customization_id = str(customization_id).strip()
        self.hotword_list = str(hotword_list).strip()
        self.input_sample_rate = int(input_sample_rate)
        self.timeout = int(timeout)
        self.replace_map = self._normalize_replace_map(replace_map)
        self.language = self._infer_language(engine_type)

    @classmethod
    def from_config(cls) -> "TencentFlashAsrClient":
        asr_cfg = config.load_config()["asr"]
        tencent_common_cfg = asr_cfg.get("tencent", {})
        flash_cfg = asr_cfg.get("tencent_asr_flash", {})
        return cls(
            app_id=tencent_common_cfg.get("app_id", ""),
            secret_id=tencent_common_cfg.get("secret_id", flash_cfg.get("secret_id", "")),
            secret_key=tencent_common_cfg.get("secret_key", flash_cfg.get("secret_key", "")),
            engine_type=flash_cfg.get("engine_type", "16k_zh"),
            speaker_diarization=flash_cfg.get("speaker_diarization", 0),
            filter_dirty=flash_cfg.get("filter_dirty", 0),
            filter_modal=flash_cfg.get("filter_modal", 0),
            filter_punc=flash_cfg.get("filter_punc", 0),
            convert_num_mode=flash_cfg.get("convert_num_mode", 1),
            word_info=flash_cfg.get("word_info", 0),
            first_channel_only=flash_cfg.get("first_channel_only", 1),
            sentence_max_length=flash_cfg.get("sentence_max_length", 0),
            hotword_id=flash_cfg.get("hotword_id", ""),
            customization_id=flash_cfg.get("customization_id", ""),
            hotword_list=flash_cfg.get("hotword_list", ""),
            input_sample_rate=flash_cfg.get("input_sample_rate", 0),
            timeout=flash_cfg.get("timeout", 120),
            replace_map=asr_cfg.get("replace_map", {}),
        )

    def transcribe(self, audio_path: str) -> dict:
        if not self.app_id or not self.secret_id or not self.secret_key:
            raise TencentFlashAsrError("Tencent flash ASR app_id/secret_id/secret_key is not configured")

        audio_bytes = self._read_audio(audio_path)
        voice_format = self._detect_voice_format(audio_path)
        timestamp = int(time.time())
        params = self._build_params(voice_format, timestamp)
        url = self._build_request_url(params)
        headers = self._build_headers(params, len(audio_bytes))

        try:
            response = httpx.post(url, content=audio_bytes, headers=headers, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise TencentFlashAsrError(f"Tencent flash ASR request failed: {e}") from e

        if response.status_code >= 400:
            detail = response.text.strip() or f"HTTP {response.status_code}"
            raise TencentFlashAsrError(f"Tencent flash ASR HTTP {response.status_code}: {detail}")

        try:
            payload = response.json()
        except ValueError as e:
            raise TencentFlashAsrError("Tencent flash ASR returned invalid JSON") from e

        if not isinstance(payload, dict):
            raise TencentFlashAsrError("Tencent flash ASR returned unexpected response")
        if int(payload.get("code", -1)) != 0:
            raise TencentFlashAsrError(str(payload.get("message", "Tencent flash ASR failed")).strip())

        return self._build_result(payload)

    def _read_audio(self, audio_path: str) -> bytes:
        try:
            with open(audio_path, "rb") as audio_file:
                audio_bytes = audio_file.read()
        except OSError as e:
            raise TencentFlashAsrError(f"Failed to read audio file: {e}") from e
        if len(audio_bytes) > self.max_audio_bytes:
            raise TencentFlashAsrError(
                f"Audio file is too large for Tencent flash upload: {len(audio_bytes)} bytes > {self.max_audio_bytes} bytes"
            )
        return audio_bytes

    def _build_params(self, voice_format: str, timestamp: int) -> dict[str, str | int]:
        params: dict[str, str | int] = {
            "appid": self.app_id,
            "secretid": self.secret_id,
            "engine_type": self.engine_type,
            "voice_format": voice_format,
            "timestamp": timestamp,
            "speaker_diarization": self.speaker_diarization,
            "filter_dirty": self.filter_dirty,
            "filter_modal": self.filter_modal,
            "filter_punc": self.filter_punc,
            "convert_num_mode": self.convert_num_mode,
            "word_info": self.word_info,
            "first_channel_only": self.first_channel_only,
        }
        if self.sentence_max_length > 0:
            params["sentence_max_length"] = self.sentence_max_length
        if self.hotword_id:
            params["hotword_id"] = self.hotword_id
        if self.customization_id:
            params["customization_id"] = self.customization_id
        if self.hotword_list:
            params["hotword_list"] = self.hotword_list
        if self.input_sample_rate > 0:
            params["input_sample_rate"] = self.input_sample_rate
        return params

    def _build_request_url(self, params: dict[str, str | int]) -> str:
        return f"{self.endpoint}/asr/flash/v1/{self.app_id}?{self._query_string(params)}"

    def _build_headers(self, params: dict[str, str | int], content_length: int) -> dict[str, str]:
        authorization = self._build_authorization(params)
        return {
            "Host": self.host,
            "Authorization": authorization,
            "Content-Type": "application/octet-stream",
            "Content-Length": str(content_length),
        }

    def _build_authorization(self, params: dict[str, str | int]) -> str:
        path = f"/asr/flash/v1/{self.app_id}"
        source = f"POST{self.host}{path}?{self._query_string(params)}"
        digest = hmac.new(self.secret_key.encode("utf-8"), source.encode("utf-8"), hashlib.sha1).digest()
        return base64.b64encode(digest).decode("utf-8")

    @staticmethod
    def _query_string(params: dict[str, str | int]) -> str:
        return urlencode(sorted(params.items(), key=lambda item: item[0]))

    def _build_result(self, payload: dict) -> dict:
        flash_result = payload.get("flash_result", [])
        if not isinstance(flash_result, list):
            flash_result = []

        segments: list[dict] = []
        texts: list[str] = []
        for channel in flash_result:
            if not isinstance(channel, dict):
                continue
            channel_sentences = channel.get("sentence_list", []) or []
            for sentence in channel_sentences:
                if not isinstance(sentence, dict):
                    continue
                text = str(sentence.get("text", "")).strip()
                words = []
                for word in sentence.get("word_list", []) or []:
                    if not isinstance(word, dict):
                        continue
                    words.append(
                        {
                            "text": str(word.get("word", "")).strip(),
                            "start_time": int(word.get("start_time", 0)),
                            "end_time": int(word.get("end_time", 0)),
                        }
                    )
                segments.append(
                    {
                        "text": text,
                        "start_time": int(sentence.get("start_time", 0)),
                        "end_time": int(sentence.get("end_time", 0)),
                        "speaker_id": int(sentence.get("speaker_id", 0)),
                        "words": words,
                        "channel_id": int(channel.get("channel_id", 0)),
                    }
                )
                if text:
                    texts.append(text)

        text_raw = "\n".join(texts).strip()
        if not text_raw:
            text_raw = "\n".join(
                str(channel.get("text", "")).strip()
                for channel in flash_result
                if isinstance(channel, dict) and str(channel.get("text", "")).strip()
            ).strip()

        return {
            "engine": "tencent_flash_asr",
            "language": self.language,
            "text_raw": text_raw,
            "text": self._apply_replace_map_to_text(text_raw),
            "segments": self._apply_replace_map_to_value(segments),
            "raw": payload,
        }

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

    @staticmethod
    def _normalize_replace_map(replace_map) -> dict[str, str]:
        if not replace_map:
            return {}
        if isinstance(replace_map, str):
            try:
                replace_map = json.loads(replace_map)
            except json.JSONDecodeError as e:
                raise TencentFlashAsrError("Invalid asr.replace_map JSON") from e
        if not isinstance(replace_map, dict):
            raise TencentFlashAsrError("asr.replace_map must be a JSON object")
        return {str(source): str(target) for source, target in replace_map.items()}

    @staticmethod
    def _detect_voice_format(audio_path: str) -> str:
        suffix = audio_path.rsplit(".", 1)[-1].lower() if "." in audio_path else ""
        mapping = {"opus": "ogg-opus"}
        voice_format = mapping.get(suffix, suffix)
        if not voice_format:
            raise TencentFlashAsrError("Unable to detect audio format from file extension")
        return voice_format

    @staticmethod
    def _infer_language(engine_type: str) -> str:
        if engine_type.startswith(("8k_zh", "16k_zh")):
            return "zh"
        if engine_type.startswith(("8k_en", "16k_en")):
            return "en"
        return engine_type
