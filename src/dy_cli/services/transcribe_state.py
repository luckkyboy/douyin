"""Helpers for transcription output and progress tracking."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone


def init_progress(root_dir: str, files: list[str]) -> dict:
    return init_progress_for_extension(root_dir, files, ".json")


def init_progress_for_extension(root_dir: str, files: list[str], extension: str) -> dict:
    items = {}
    completed = 0
    for filename in files:
        output_file = os.path.splitext(filename)[0] + extension
        status = "done" if os.path.exists(os.path.join(root_dir, output_file)) else "pending"
        if status == "done":
            completed += 1
        items[filename] = {"status": status, "output_file": output_file}

    return {
        "version": 1,
        "root_dir": root_dir,
        "total": len(files),
        "completed": completed,
        "last_index": 0,
        "last_file": "",
        "updated_at": "",
        "items": items,
    }


def save_progress(progress_path: str, progress: dict) -> None:
    os.makedirs(os.path.dirname(progress_path) or ".", exist_ok=True)
    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def mark_progress(
    progress: dict,
    progress_path: str,
    filename: str,
    index: int,
    status: str,
    *,
    output_file: str | None = None,
    output_json: str | None = None,
    error: str | None = None,
) -> None:
    item = progress["items"].setdefault(filename, {"status": "pending"})
    item["status"] = status
    if output_file is None and output_json is not None:
        output_file = output_json
    if output_file:
        item["output_file"] = output_file
        if output_file.endswith(".json"):
            item["output_json"] = output_file
    if error:
        item["error"] = error
    else:
        item.pop("error", None)

    progress["completed"] = sum(1 for data in progress["items"].values() if data.get("status") == "done")
    progress["last_index"] = index
    progress["last_file"] = filename
    progress["updated_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    save_progress(progress_path, progress)


def write_transcript_json(output_path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    temp_path = f"{output_path}.part"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, output_path)


def write_transcript_srt(output_path: str, segments: list[dict]) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    temp_path = f"{output_path}.part"
    lines: list[str] = []
    for index, segment in enumerate(segments, 1):
        start_time = _normalize_segment_time(segment.get("start_time", segment.get("start", 0)))
        end_time = _normalize_segment_time(segment.get("end_time", segment.get("end", 0)))
        text = str(segment.get("text", "")).strip()
        lines.append(str(index))
        lines.append(f"{_format_srt_timestamp(start_time)} --> {_format_srt_timestamp(end_time)}")
        lines.append(text)
        lines.append("")
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    os.replace(temp_path, output_path)


def _normalize_segment_time(value) -> int:
    if isinstance(value, float):
        return int(round(value * 1000))
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _format_srt_timestamp(milliseconds: int) -> str:
    total_seconds, ms = divmod(max(milliseconds, 0), 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"
