import json

from dy_cli.services.transcribe_state import (
    init_progress,
    mark_progress,
    write_transcript_json,
)


def test_init_progress_marks_existing_json_as_done(tmp_path):
    root_dir = tmp_path
    (root_dir / "001_alpha.mp4").write_bytes(b"video")
    (root_dir / "002_beta.mp4").write_bytes(b"video")
    (root_dir / "001_alpha.json").write_text("{}", encoding="utf-8")

    progress = init_progress(str(root_dir), ["001_alpha.mp4", "002_beta.mp4"])

    assert progress["total"] == 2
    assert progress["completed"] == 1
    assert progress["items"]["001_alpha.mp4"]["status"] == "done"
    assert progress["items"]["002_beta.mp4"]["status"] == "pending"


def test_mark_progress_updates_completed_and_last_file(tmp_path):
    progress_path = tmp_path / "transcribe_progress.json"
    progress = {
        "version": 1,
        "root_dir": str(tmp_path),
        "total": 2,
        "completed": 0,
        "last_index": 0,
        "last_file": "",
        "updated_at": "",
        "items": {
            "001_alpha.mp4": {"status": "pending"},
            "002_beta.mp4": {"status": "pending"},
        },
    }

    mark_progress(progress, str(progress_path), "001_alpha.mp4", 1, "done", output_json="001_alpha.json")

    saved = json.loads(progress_path.read_text(encoding="utf-8"))
    assert saved["completed"] == 1
    assert saved["last_index"] == 1
    assert saved["last_file"] == "001_alpha.mp4"
    assert saved["items"]["001_alpha.mp4"]["status"] == "done"
    assert saved["items"]["001_alpha.mp4"]["output_json"] == "001_alpha.json"


def test_output_json_written_with_part_then_renamed(tmp_path):
    output_path = tmp_path / "001_alpha.json"

    write_transcript_json(str(output_path), {"text": "hello"})

    assert output_path.exists()
    assert not (tmp_path / "001_alpha.json.part").exists()
    assert json.loads(output_path.read_text(encoding="utf-8")) == {"text": "hello"}
