import json
from ast import parse
from pathlib import Path

from click.testing import CliRunner

from dy_cli.commands.download import download


class _FakeAPIClient:
    def __init__(self):
        self.closed = False

    def get_download_url(self, aweme_id):
        return {
            "video_url": "https://api.example.com/video.mp4",
            "desc": "demo",
            "author": "tester",
        }

    def download_file(self, url, output_path, progress_callback=None):
        with open(output_path, "wb") as f:
            f.write(b"video")
        if progress_callback is not None:
            progress_callback(5, 5)

    def close(self):
        self.closed = True


class _FakePlaywrightClient:
    def __init__(self, account=None, headless=False):
        self.account = account
        self.headless = headless

    def get_video_current_src(self, aweme_id):
        return "https://playwright.example.com/video.mp4"


def test_download_prefers_playwright_current_src(monkeypatch, tmp_path):
    fake_api = _FakeAPIClient()

    monkeypatch.setattr("dy_cli.commands.download.resolve_id", lambda value: value)
    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr(
        "dy_cli.commands.download.DouyinAPIClient.from_config",
        lambda account: fake_api,
    )
    monkeypatch.setattr(
        "dy_cli.commands.download.PlaywrightClient",
        _FakePlaywrightClient,
    )

    result = CliRunner().invoke(download, ["1234567890123456789", "--json-output"])

    assert result.exit_code == 0
    assert "https://playwright.example.com/video.mp4" in result.output
    assert fake_api.closed is True


class _FakeBatchAPIClient:
    def __init__(self, pages):
        self.pages = pages
        self.closed = False
        self.page_calls = []
        self.downloaded = []

    def get_user_profile(self, sec_user_id):
        return {"nickname": "tester"}

    def get_user_posts(self, sec_user_id, max_cursor=0, count=20):
        self.page_calls.append((sec_user_id, max_cursor, count))
        return self.pages[max_cursor]

    def get_download_url(self, aweme_id):
        return {
            "video_url": f"https://api.example.com/{aweme_id}.mp4",
            "desc": f"desc-{aweme_id}",
            "author": "tester",
        }

    def download_file(self, url, output_path, progress_callback=None):
        self.downloaded.append((url, output_path))
        with open(output_path, "wb") as f:
            f.write(b"video")
        if progress_callback is not None:
            progress_callback(5, 5)

    def close(self):
        self.closed = True


def test_batch_user_download_fetches_all_pages_and_sleeps_between_items(monkeypatch, tmp_path):
    fake_api = _FakeBatchAPIClient(
        {
            0: {
                "aweme_list": [
                    {"aweme_id": "1001", "desc": "first"},
                    {"aweme_id": "1002", "desc": "second"},
                ],
                "has_more": 1,
                "max_cursor": 2,
            },
            2: {
                "aweme_list": [
                    {"aweme_id": "1003", "desc": "third"},
                ],
                "has_more": 0,
                "max_cursor": 3,
            },
        }
    )
    sleep_calls = []

    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr(
        "dy_cli.commands.download.DouyinAPIClient.from_config",
        lambda account: fake_api,
    )
    monkeypatch.setattr("time.sleep", lambda seconds: sleep_calls.append(seconds))

    result = CliRunner().invoke(download, ["SEC_UID", "--user"])
    export_path = tmp_path / "tester" / "tester_posts.json"

    assert result.exit_code == 0
    assert export_path.exists()
    exported = json.loads(export_path.read_text(encoding="utf-8"))
    assert exported["sec_user_id"] == "SEC_UID"
    assert exported["nickname"] == "tester"
    assert exported["complete"] is True
    assert exported["total"] == 3
    assert [item["aweme_id"] for item in exported["posts"]] == [
        "1001",
        "1002",
        "1003",
    ]
    assert fake_api.page_calls == [("SEC_UID", 0, 20), ("SEC_UID", 2, 20)]
    assert [url for url, _ in fake_api.downloaded] == [
        "https://api.example.com/1001.mp4",
        "https://api.example.com/1002.mp4",
        "https://api.example.com/1003.mp4",
    ]
    assert sleep_calls == [10, 10]
    assert fake_api.closed is True


def test_batch_user_download_respects_limit_across_pages(monkeypatch, tmp_path):
    fake_api = _FakeBatchAPIClient(
        {
            0: {
                "aweme_list": [
                    {"aweme_id": "1001", "desc": "first"},
                    {"aweme_id": "1002", "desc": "second"},
                ],
                "has_more": 1,
                "max_cursor": 2,
            },
            2: {
                "aweme_list": [
                    {"aweme_id": "1003", "desc": "third"},
                ],
                "has_more": 0,
                "max_cursor": 3,
            },
        }
    )
    sleep_calls = []

    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr(
        "dy_cli.commands.download.DouyinAPIClient.from_config",
        lambda account: fake_api,
    )
    monkeypatch.setattr("time.sleep", lambda seconds: sleep_calls.append(seconds))

    result = CliRunner().invoke(download, ["SEC_UID", "--user", "--limit", "2"])

    assert result.exit_code == 0
    assert fake_api.page_calls == [("SEC_UID", 0, 2)]
    assert [url for url, _ in fake_api.downloaded] == [
        "https://api.example.com/1001.mp4",
        "https://api.example.com/1002.mp4",
    ]
    assert sleep_calls == [10]
    assert fake_api.closed is True


def test_batch_user_download_reuses_complete_posts_cache(monkeypatch, tmp_path):
    fake_api = _FakeBatchAPIClient({})
    user_dir = tmp_path / "tester"
    user_dir.mkdir()
    export_path = user_dir / "tester_posts.json"
    export_path.write_text(
        json.dumps(
            {
                "sec_user_id": "SEC_UID",
                "nickname": "tester",
                "complete": True,
                "total": 2,
                "posts": [
                    {"aweme_id": "1001", "desc": "first"},
                    {"aweme_id": "1002", "desc": "second"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    sleep_calls = []

    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr(
        "dy_cli.commands.download.DouyinAPIClient.from_config",
        lambda account: fake_api,
    )
    monkeypatch.setattr("time.sleep", lambda seconds: sleep_calls.append(seconds))

    result = CliRunner().invoke(download, ["SEC_UID", "--user"])

    assert result.exit_code == 0
    assert fake_api.page_calls == []
    assert [url for url, _ in fake_api.downloaded] == [
        "https://api.example.com/1001.mp4",
        "https://api.example.com/1002.mp4",
    ]
    assert sleep_calls == [10]
    assert fake_api.closed is True


def test_batch_user_download_skips_existing_media_files(monkeypatch, tmp_path):
    fake_api = _FakeBatchAPIClient(
        {
            0: {
                "aweme_list": [
                    {"aweme_id": "1001", "desc": "first"},
                    {"aweme_id": "1002", "desc": "second"},
                ],
                "has_more": 0,
                "max_cursor": 0,
            },
        }
    )
    user_dir = tmp_path / "tester"
    user_dir.mkdir()
    (user_dir / "001_first.mp4").write_bytes(b"existing")
    sleep_calls = []

    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr(
        "dy_cli.commands.download.DouyinAPIClient.from_config",
        lambda account: fake_api,
    )
    monkeypatch.setattr("time.sleep", lambda seconds: sleep_calls.append(seconds))

    result = CliRunner().invoke(download, ["SEC_UID", "--user"])

    assert result.exit_code == 0
    assert [url for url, _ in fake_api.downloaded] == [
        "https://api.example.com/1002.mp4",
    ]
    assert sleep_calls == [10]


def test_batch_user_download_writes_progress_file(monkeypatch, tmp_path):
    fake_api = _FakeBatchAPIClient(
        {
            0: {
                "aweme_list": [
                    {"aweme_id": "1001", "desc": "first"},
                    {"aweme_id": "1002", "desc": "second"},
                ],
                "has_more": 0,
                "max_cursor": 0,
            },
        }
    )
    sleep_calls = []

    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr(
        "dy_cli.commands.download.DouyinAPIClient.from_config",
        lambda account: fake_api,
    )
    monkeypatch.setattr("time.sleep", lambda seconds: sleep_calls.append(seconds))

    result = CliRunner().invoke(download, ["SEC_UID", "--user"])
    progress_path = tmp_path / "tester" / "tester_progress.json"

    assert result.exit_code == 0
    assert progress_path.exists()
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    assert progress["sec_user_id"] == "SEC_UID"
    assert progress["completed"] == 2
    assert progress["last_index"] == 2
    assert progress["last_aweme_id"] == "1002"
    assert progress["items"]["1001"]["status"] == "done"
    assert progress["items"]["1002"]["status"] == "done"
    assert sleep_calls == [10]


def test_batch_user_download_resumes_from_failed_item(monkeypatch, tmp_path):
    fake_api = _FakeBatchAPIClient({})
    user_dir = tmp_path / "tester"
    user_dir.mkdir()
    (user_dir / "001_first.mp4").write_bytes(b"existing")
    (user_dir / "tester_posts.json").write_text(
        json.dumps(
            {
                "sec_user_id": "SEC_UID",
                "nickname": "tester",
                "complete": True,
                "total": 3,
                "posts": [
                    {"aweme_id": "1001", "desc": "first"},
                    {"aweme_id": "1002", "desc": "second"},
                    {"aweme_id": "1003", "desc": "third"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (user_dir / "tester_progress.json").write_text(
        json.dumps(
            {
                "sec_user_id": "SEC_UID",
                "manifest_file": "tester_posts.json",
                "total": 3,
                "completed": 1,
                "last_index": 1,
                "last_aweme_id": "1001",
                "items": {
                    "1001": {"status": "done", "file": "001_first.mp4"},
                    "1002": {"status": "failed", "error": "timeout"},
                    "1003": {"status": "pending"},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    sleep_calls = []

    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr(
        "dy_cli.commands.download.DouyinAPIClient.from_config",
        lambda account: fake_api,
    )
    monkeypatch.setattr("time.sleep", lambda seconds: sleep_calls.append(seconds))

    result = CliRunner().invoke(download, ["SEC_UID", "--user"])
    progress = json.loads((user_dir / "tester_progress.json").read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert [url for url, _ in fake_api.downloaded] == [
        "https://api.example.com/1002.mp4",
        "https://api.example.com/1003.mp4",
    ]
    assert progress["completed"] == 3
    assert progress["last_index"] == 3
    assert progress["last_aweme_id"] == "1003"
    assert progress["items"]["1001"]["status"] == "done"
    assert progress["items"]["1002"]["status"] == "done"
    assert progress["items"]["1003"]["status"] == "done"
    assert sleep_calls == [10, 10]


def test_download_command_source_parses_with_python_310_grammar():
    source = Path("src/dy_cli/commands/download.py").read_text(encoding="utf-8")

    parse(source, filename="download.py", feature_version=(3, 10))
