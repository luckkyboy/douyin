"""Helpers for transcription output and progress tracking."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone


def init_progress(root_dir: str, files: list[str]) -> dict:
    items = {}
    completed = 0
    for filename in files:
        output_json = os.path.splitext(filename)[0] + ".json"
        status = "done" if os.path.exists(os.path.join(root_dir, output_json)) else "pending"
        if status == "done":
            completed += 1
        items[filename] = {"status": status, "output_json": output_json}

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
    output_json: str | None = None,
    error: str | None = None,
) -> None:
    item = progress["items"].setdefault(filename, {"status": "pending"})
    item["status"] = status
    if output_json:
        item["output_json"] = output_json
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
