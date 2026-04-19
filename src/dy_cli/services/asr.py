"""ASR provider factory."""
from __future__ import annotations

from dy_cli.services.tencent_asr import TencentAsrClient, TencentAsrError
from dy_cli.services.whisper_webservice import WhisperWebserviceClient, WhisperWebserviceError
from dy_cli.utils import config

AsrError = (WhisperWebserviceError, TencentAsrError)


def create_asr_client():
    provider = str(config.get("asr.provider", "whisper_webservice") or "whisper_webservice").strip()
    if provider == "whisper_webservice":
        return WhisperWebserviceClient.from_config()
    if provider == "tencent_asr":
        return TencentAsrClient.from_config()
    raise ValueError(f"Unsupported ASR provider: {provider}")
