"""dy transcribe — 转写本地视频为文本 JSON。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import click

from dy_cli.services.media import MediaError, extract_audio
from dy_cli.services.whisper_webservice import WhisperWebserviceClient, WhisperWebserviceError
from dy_cli.services.transcribe_state import init_progress, mark_progress, save_progress, write_transcript_json
from dy_cli.utils.output import info, success, warning

AUDIO_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}


@click.command("transcribe", help="转写本地视频为文本 JSON")
@click.argument("path", type=click.Path(exists=True, path_type=str))
@click.option("--force", is_flag=True, help="已有同名 JSON 也重新转写")
@click.option("--audio-keep", is_flag=True, help="保留中间音频文件")
@click.option("--delete-video", is_flag=True, help="转写成功后删除原视频，保留 mp3 和 json")
@click.option("--limit", type=int, default=0, help="目录模式下仅处理前 N 个视频")
def transcribe(path: str, force: bool, audio_keep: bool, delete_video: bool, limit: int):
    """对本地已下载视频进行语音转写。"""
    client = WhisperWebserviceClient.from_config()

    if os.path.isfile(path):
        _transcribe_file(path, client, force=force, audio_keep=audio_keep, delete_video=delete_video)
        return

    _transcribe_dir(path, client, force=force, audio_keep=audio_keep, delete_video=delete_video, limit=limit)


def _transcribe_dir(
    path: str,
    client: WhisperWebserviceClient,
    *,
    force: bool,
    audio_keep: bool,
    delete_video: bool,
    limit: int,
) -> None:
    files = sorted(name for name in os.listdir(path) if _is_supported_media_file(name))
    if limit > 0:
        files = files[:limit]
    if not files:
        warning("目录下未找到支持的音视频文件")
        return

    progress_path = os.path.join(path, "transcribe_progress.json")
    progress = _load_or_init_progress(progress_path, path, files)

    for index, filename in enumerate(files, 1):
        file_path = os.path.join(path, filename)
        output_json = os.path.splitext(file_path)[0] + ".json"

        if os.path.exists(output_json) and not force:
            info(f"[{index}/{len(files)}] 已存在转写结果，跳过: {filename}")
            mark_progress(progress, progress_path, filename, index, "done", output_json=os.path.basename(output_json))
            continue

        try:
            _transcribe_file(file_path, client, force=force, audio_keep=audio_keep, delete_video=delete_video)
            mark_progress(progress, progress_path, filename, index, "done", output_json=os.path.basename(output_json))
        except (MediaError, WhisperWebserviceError) as e:
            warning(f"[{index}/{len(files)}] 转写失败: {filename} ({e})")
            mark_progress(progress, progress_path, filename, index, "failed", output_json=os.path.basename(output_json), error=str(e))

    success(f"转写完成: {path}")


def _transcribe_file(
    path: str,
    client: WhisperWebserviceClient,
    *,
    force: bool,
    audio_keep: bool,
    delete_video: bool,
) -> None:
    output_json = os.path.splitext(path)[0] + ".json"
    if os.path.exists(output_json) and not force:
        info(f"已存在转写结果，跳过: {os.path.basename(path)}")
        return

    source_is_audio = _is_audio_file(path)
    audio_path = path if source_is_audio else os.path.splitext(path)[0] + ".transcribe.mp3"
    if not source_is_audio:
        temp_audio_path = os.path.splitext(path)[0] + ".transcribe.part.mp3"
        extract_audio(path, temp_audio_path)
        os.replace(temp_audio_path, audio_path)

    try:
        result = client.transcribe(audio_path)
        payload = {
            "version": 1,
            "source_file": os.path.basename(path),
            "engine": result.get("engine", "transcribe"),
            "language": result.get("language", getattr(client, "language", "")),
            "text_raw": result.get("text_raw", result["text"]),
            "text": result["text"],
            "segments": result["segments"],
            "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "asr_raw": result["raw"],
        }
        write_transcript_json(output_json, payload)
        success(f"转写成功: {os.path.basename(output_json)}")
        if delete_video and not source_is_audio and os.path.exists(path):
            os.remove(path)
    finally:
        keep_audio = source_is_audio or audio_keep or delete_video
        if not keep_audio and os.path.exists(audio_path):
            os.remove(audio_path)


def _load_or_init_progress(progress_path: str, root_dir: str, files: list[str]) -> dict:
    if os.path.exists(progress_path):
        try:
            with open(progress_path, encoding="utf-8") as f:
                progress = json.load(f)
            if isinstance(progress, dict) and progress.get("root_dir") == root_dir:
                progress["items"] = progress.get("items", {})
                for filename in files:
                    progress["items"].setdefault(
                        filename,
                        {"status": "done" if os.path.exists(os.path.join(root_dir, os.path.splitext(filename)[0] + ".json")) else "pending",
                         "output_json": os.path.splitext(filename)[0] + ".json"},
                    )
                progress["total"] = len(files)
                progress["completed"] = sum(
                    1
                    for filename in files
                    if os.path.exists(os.path.join(root_dir, os.path.splitext(filename)[0] + ".json"))
                )
                save_progress(progress_path, progress)
                return progress
        except (OSError, json.JSONDecodeError):
            warning("转写进度文件读取失败，重新初始化")

    progress = init_progress(root_dir, files)
    save_progress(progress_path, progress)
    return progress


def _is_audio_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in AUDIO_EXTENSIONS


def _is_supported_media_file(path: str) -> bool:
    suffix = os.path.splitext(path)[1].lower()
    return suffix == ".mp4" or suffix in AUDIO_EXTENSIONS
