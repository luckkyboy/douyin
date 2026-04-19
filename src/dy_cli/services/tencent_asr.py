"""Tencent Cloud recording ASR client."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from copy import deepcopy
from datetime import UTC, datetime

import httpx

from dy_cli.utils import config


class TencentAsrError(Exception):
    """Raised when Tencent ASR fails."""


class TencentAsrClient:
    """Client for Tencent Cloud CreateRecTask / DescribeTaskStatus."""

    endpoint = "https://asr.tencentcloudapi.com"
    host = "asr.tencentcloudapi.com"
    service = "asr"
    version = "2019-06-14"
    max_inline_audio_bytes = 5 * 1024 * 1024

    def __init__(
        self,
        *,
        secret_id: str,
        secret_key: str,
        region: str = "ap-shanghai",
        engine_model_type: str = "16k_zh",
        channel_num: int = 1,
        res_text_format: int = 3,
        convert_num_mode: int = 1,
        speaker_diarization: int = 0,
        poll_interval_seconds: int = 5,
        max_wait_seconds: int = 1800,
        timeout: int = 60,
        replace_map: dict[str, str] | None = None,
    ):
        self.secret_id = secret_id.strip()
        self.secret_key = secret_key.strip()
        self.region = region
        self.engine_model_type = engine_model_type
        self.channel_num = int(channel_num)
        self.res_text_format = int(res_text_format)
        self.convert_num_mode = int(convert_num_mode)
        self.speaker_diarization = int(speaker_diarization)
        self.poll_interval_seconds = max(int(poll_interval_seconds), 1)
        self.max_wait_seconds = max(int(max_wait_seconds), self.poll_interval_seconds)
        self.timeout = int(timeout)
        self.replace_map = self._normalize_replace_map(replace_map)
        self.language = self._infer_language(engine_model_type)

    @classmethod
    def from_config(cls) -> "TencentAsrClient":
        asr_cfg = config.load_config()["asr"]
        tencent_cfg = asr_cfg.get("tencent_asr", {})
        return cls(
            secret_id=tencent_cfg.get("secret_id", ""),
            secret_key=tencent_cfg.get("secret_key", ""),
            region=tencent_cfg.get("region", "ap-shanghai"),
            engine_model_type=tencent_cfg.get("engine_model_type", "16k_zh"),
            channel_num=tencent_cfg.get("channel_num", 1),
            res_text_format=tencent_cfg.get("res_text_format", 3),
            convert_num_mode=tencent_cfg.get("convert_num_mode", 1),
            speaker_diarization=tencent_cfg.get("speaker_diarization", 0),
            poll_interval_seconds=tencent_cfg.get("poll_interval_seconds", 5),
            max_wait_seconds=tencent_cfg.get("max_wait_seconds", 1800),
            timeout=tencent_cfg.get("timeout", 60),
            replace_map=asr_cfg.get("replace_map", {}),
        )

    def transcribe(self, audio_path: str) -> dict:
        if not self.secret_id or not self.secret_key:
            raise TencentAsrError("Tencent ASR secret_id/secret_key is not configured")

        audio_bytes = self._read_audio(audio_path)
        task = self._create_task(audio_bytes)
        task_status = self._poll_task(task["TaskId"])
        return self._build_result(task_status)

    def _read_audio(self, audio_path: str) -> bytes:
        try:
            with open(audio_path, "rb") as audio_file:
                audio_bytes = audio_file.read()
        except OSError as e:
            raise TencentAsrError(f"Failed to read audio file: {e}") from e
        if len(audio_bytes) > self.max_inline_audio_bytes:
            raise TencentAsrError(
                f"Audio file is too large for Tencent inline upload: {len(audio_bytes)} bytes > {self.max_inline_audio_bytes} bytes"
            )
        return audio_bytes

    def _create_task(self, audio_bytes: bytes) -> dict:
        payload = {
            "EngineModelType": self.engine_model_type,
            "ChannelNum": self.channel_num,
            "ResTextFormat": self.res_text_format,
            "SourceType": 1,
            "Data": base64.b64encode(audio_bytes).decode("utf-8"),
            "DataLen": len(audio_bytes),
            "ConvertNumMode": self.convert_num_mode,
            "SpeakerDiarization": self.speaker_diarization,
        }
        response = self._request("CreateRecTask", payload)
        data = response.get("Data")
        if not isinstance(data, dict) or "TaskId" not in data:
            raise TencentAsrError("Tencent ASR CreateRecTask returned unexpected response")
        return data

    def _poll_task(self, task_id: int) -> dict:
        deadline = time.time() + self.max_wait_seconds
        while True:
            response = self._request("DescribeTaskStatus", {"TaskId": int(task_id)})
            data = response.get("Data")
            if not isinstance(data, dict):
                raise TencentAsrError("Tencent ASR DescribeTaskStatus returned unexpected response")

            status = int(data.get("Status", -1))
            if status == 2:
                return data
            if status == 3:
                raise TencentAsrError(data.get("ErrorMsg") or "Tencent ASR task failed")
            if time.time() >= deadline:
                raise TencentAsrError(f"Tencent ASR polling timed out after {self.max_wait_seconds} seconds")
            time.sleep(self.poll_interval_seconds)

    def _request(self, action: str, payload: dict) -> dict:
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        timestamp = int(time.time())
        headers = self._build_headers(action, payload_json, timestamp)

        try:
            response = httpx.post(
                self.endpoint,
                content=payload_json.encode("utf-8"),
                headers=headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise TencentAsrError(f"Tencent ASR request failed: {e}") from e

        if response.status_code >= 400:
            detail = response.text.strip() or f"HTTP {response.status_code}"
            raise TencentAsrError(f"Tencent ASR HTTP {response.status_code}: {detail}")

        try:
            data = response.json()
        except ValueError as e:
            raise TencentAsrError("Tencent ASR returned invalid JSON") from e

        if not isinstance(data, dict) or not isinstance(data.get("Response"), dict):
            raise TencentAsrError("Tencent ASR returned unexpected response")

        response_body = data["Response"]
        if "Error" in response_body:
            error = response_body["Error"]
            code = error.get("Code", "UnknownError")
            message = error.get("Message", "")
            raise TencentAsrError(f"{code}: {message}".strip(": "))
        return response_body

    def _build_headers(self, action: str, payload_json: str, timestamp: int) -> dict[str, str]:
        date = datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%d")
        canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{self.host}\n"
        signed_headers = "content-type;host"
        canonical_request = "\n".join(
            [
                "POST",
                "/",
                "",
                canonical_headers,
                signed_headers,
                hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
            ]
        )
        credential_scope = f"{date}/{self.service}/tc3_request"
        string_to_sign = "\n".join(
            [
                "TC3-HMAC-SHA256",
                str(timestamp),
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        secret_date = self._sign(f"TC3{self.secret_key}".encode("utf-8"), date)
        secret_service = self._sign(secret_date, self.service)
        secret_signing = self._sign(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            "TC3-HMAC-SHA256 "
            f"Credential={self.secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )
        return {
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": self.host,
            "X-TC-Action": action,
            "X-TC-Version": self.version,
            "X-TC-Region": self.region,
            "X-TC-Timestamp": str(timestamp),
        }

    def _build_result(self, task_status: dict) -> dict:
        result_detail = task_status.get("ResultDetail", [])
        if not isinstance(result_detail, list):
            result_detail = []
        text_raw = self._build_text_raw(task_status, result_detail)
        segments = self._build_segments(result_detail)
        return {
            "engine": "tencent_asr",
            "language": self.language,
            "text_raw": text_raw,
            "text": self._apply_replace_map_to_text(text_raw),
            "segments": self._apply_replace_map_to_value(segments),
            "raw": task_status,
        }

    def _build_text_raw(self, task_status: dict, result_detail: list[dict]) -> str:
        sentences = [str(item.get("FinalSentence", "")).strip() for item in result_detail]
        sentences = [sentence for sentence in sentences if sentence]
        if sentences:
            return "\n".join(sentences)
        return str(task_status.get("Result", "") or "").strip()

    def _build_segments(self, result_detail: list[dict]) -> list[dict]:
        segments: list[dict] = []
        for item in result_detail:
            words = []
            for word in item.get("Words", []) or []:
                if not isinstance(word, dict):
                    continue
                words.append(
                    {
                        "text": str(word.get("Word", "")).strip(),
                        "start_time": int(word.get("OffsetStartMs", 0)),
                        "end_time": int(word.get("OffsetEndMs", 0)),
                    }
                )
            segments.append(
                {
                    "text": str(item.get("FinalSentence", "")).strip(),
                    "start_time": int(item.get("StartMs", 0)),
                    "end_time": int(item.get("EndMs", 0)),
                    "speaker_id": int(item.get("SpeakerId", 0)),
                    "words": words,
                }
            )
        return segments

    @staticmethod
    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

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
                raise TencentAsrError("Invalid asr.replace_map JSON") from e
        if not isinstance(replace_map, dict):
            raise TencentAsrError("asr.replace_map must be a JSON object")
        return {str(source): str(target) for source, target in replace_map.items()}

    @staticmethod
    def _infer_language(engine_model_type: str) -> str:
        if engine_model_type.startswith(("8k_zh", "16k_zh")):
            return "zh"
        if engine_model_type.startswith(("8k_en", "16k_en")):
            return "en"
        return engine_model_type
