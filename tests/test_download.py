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


def test_single_download_with_audio_keeps_video_and_creates_mp3(monkeypatch, tmp_path):
    fake_api = _FakeAPIClient()
    extract_calls = []

    def fake_extract(video_path, audio_path):
        extract_calls.append((video_path, audio_path))
        with open(audio_path, "wb") as f:
            f.write(b"audio")

    monkeypatch.setattr("dy_cli.commands.download.resolve_id", lambda value: value)
    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr("dy_cli.commands.download.DouyinAPIClient.from_config", lambda account: fake_api)
    monkeypatch.setattr("dy_cli.commands.download.PlaywrightClient", _FakePlaywrightClient)
    monkeypatch.setattr("dy_cli.commands.download.extract_audio", fake_extract)

    result = CliRunner().invoke(download, ["1234567890123456789", "--audio"])

    assert result.exit_code == 0
    assert (tmp_path / "tester_demo.mp4").exists()
    assert (tmp_path / "tester_demo.mp3").exists()
    assert extract_calls == [(str(tmp_path / "tester_demo.mp4"), str(tmp_path / "tester_demo.part.mp3"))]


def test_single_download_with_audio_delete_video_removes_mp4(monkeypatch, tmp_path):
    fake_api = _FakeAPIClient()

    def fake_extract(video_path, audio_path):
        with open(audio_path, "wb") as f:
            f.write(b"audio")

    monkeypatch.setattr("dy_cli.commands.download.resolve_id", lambda value: value)
    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr("dy_cli.commands.download.DouyinAPIClient.from_config", lambda account: fake_api)
    monkeypatch.setattr("dy_cli.commands.download.PlaywrightClient", _FakePlaywrightClient)
    monkeypatch.setattr("dy_cli.commands.download.extract_audio", fake_extract)

    result = CliRunner().invoke(download, ["1234567890123456789", "--audio-delete-video"])

    assert result.exit_code == 0
    assert not (tmp_path / "tester_demo.mp4").exists()
    assert (tmp_path / "tester_demo.mp3").exists()


def test_single_download_rejects_audio_flags_together(monkeypatch, tmp_path):
    monkeypatch.setattr("dy_cli.commands.download.resolve_id", lambda value: value)
    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )

    result = CliRunner().invoke(download, ["1234567890123456789", "--audio", "--audio-delete-video"])

    assert result.exit_code == 1
    assert "不能同时使用" in result.output


class _FakeBatchPlaywrightClient:
    def __init__(self, account=None, headless=False):
        self.account = account
        self.headless = headless
        self.calls = []

    def get_video_current_src(self, aweme_id):
        self.calls.append(aweme_id)
        return f"https://playwright.example.com/{aweme_id}.mp4"


class _FailingBatchPlaywrightClient:
    def __init__(self, account=None, headless=False):
        self.account = account
        self.headless = headless

    def get_video_current_src(self, aweme_id):
        from dy_cli.engines.playwright_client import PlaywrightError

        raise PlaywrightError("boom")


class _FakeBatchAPIClient:
    def __init__(self, pages):
        self.pages = pages
        self.closed = False
        self.page_calls = []
        self.downloaded = []
        self.download_url_calls = []

    def get_user_profile(self, sec_user_id):
        return {"nickname": "tester"}

    def get_user_posts(self, sec_user_id, max_cursor=0, count=20):
        self.page_calls.append((sec_user_id, max_cursor, count))
        return self.pages[max_cursor]

    def get_download_url(self, aweme_id):
        self.download_url_calls.append(aweme_id)
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


def test_batch_user_download_prefers_playwright_current_src(monkeypatch, tmp_path):
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
    fake_playwright = _FakeBatchPlaywrightClient(account="browser", headless=True)

    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr(
        "dy_cli.commands.download.DouyinAPIClient.from_config",
        lambda account: fake_api,
    )
    monkeypatch.setattr("dy_cli.commands.download.PlaywrightClient", lambda account=None, headless=False: fake_playwright)
    monkeypatch.setattr("time.sleep", lambda seconds: sleep_calls.append(seconds))

    result = CliRunner().invoke(download, ["SEC_UID", "--user"])

    assert result.exit_code == 0
    assert fake_playwright.calls == ["1001", "1002"]
    assert [url for url, _ in fake_api.downloaded] == [
        "https://playwright.example.com/1001.mp4",
        "https://playwright.example.com/1002.mp4",
    ]
    assert sleep_calls == [10]


def test_batch_user_download_falls_back_to_api_when_playwright_fails(monkeypatch, tmp_path):
    fake_api = _FakeBatchAPIClient(
        {
            0: {
                "aweme_list": [
                    {"aweme_id": "1001", "desc": "first"},
                ],
                "has_more": 0,
                "max_cursor": 0,
            },
        }
    )

    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr(
        "dy_cli.commands.download.DouyinAPIClient.from_config",
        lambda account: fake_api,
    )
    monkeypatch.setattr("dy_cli.commands.download.PlaywrightClient", _FailingBatchPlaywrightClient)

    result = CliRunner().invoke(download, ["SEC_UID", "--user"])

    assert result.exit_code == 0
    assert [url for url, _ in fake_api.downloaded] == [
        "https://api.example.com/1001.mp4",
    ]


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
    assert sleep_calls == []


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
    assert sleep_calls == [10]


def test_batch_user_download_prefers_existing_files_over_progress_state(monkeypatch, tmp_path):
    fake_api = _FakeBatchAPIClient({})
    user_dir = tmp_path / "tester"
    user_dir.mkdir()
    (user_dir / "tester_posts.json").write_text(
        json.dumps(
            {
                "sec_user_id": "SEC_UID",
                "nickname": "tester",
                "complete": True,
                "total": 1,
                "posts": [
                    {"aweme_id": "1001", "desc": "first"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (user_dir / "001_first.mp4").write_bytes(b"existing")
    (user_dir / "tester_progress.json").write_text(
        json.dumps(
            {
                "sec_user_id": "SEC_UID",
                "manifest_file": "tester_posts.json",
                "total": 1,
                "completed": 0,
                "last_index": 0,
                "last_aweme_id": "",
                "items": {
                    "1001": {"status": "failed", "error": "timeout"},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr(
        "dy_cli.commands.download.DouyinAPIClient.from_config",
        lambda account: fake_api,
    )

    result = CliRunner().invoke(download, ["SEC_UID", "--user"])
    progress = json.loads((user_dir / "tester_progress.json").read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert fake_api.download_url_calls == []
    assert fake_api.downloaded == []
    assert progress["completed"] == 1
    assert progress["items"]["1001"]["status"] == "done"


def test_batch_user_download_matches_existing_files_ignoring_numeric_prefix(monkeypatch, tmp_path):
    fake_api = _FakeBatchAPIClient({})
    user_dir = tmp_path / "tester"
    user_dir.mkdir()
    (user_dir / "tester_posts.json").write_text(
        json.dumps(
            {
                "sec_user_id": "SEC_UID",
                "nickname": "tester",
                "complete": True,
                "total": 1,
                "posts": [
                    {"aweme_id": "1001", "desc": "first"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (user_dir / "087_first.mp4").write_bytes(b"existing")

    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr(
        "dy_cli.commands.download.DouyinAPIClient.from_config",
        lambda account: fake_api,
    )

    result = CliRunner().invoke(download, ["SEC_UID", "--user"])
    progress = json.loads((user_dir / "tester_progress.json").read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert fake_api.download_url_calls == []
    assert fake_api.downloaded == []
    assert progress["completed"] == 1
    assert progress["items"]["1001"]["status"] == "done"


def test_batch_user_download_skips_when_matching_mp3_exists(monkeypatch, tmp_path):
    fake_api = _FakeBatchAPIClient({})
    user_dir = tmp_path / "tester"
    user_dir.mkdir()
    (user_dir / "tester_posts.json").write_text(
        json.dumps(
            {
                "sec_user_id": "SEC_UID",
                "nickname": "tester",
                "complete": True,
                "total": 1,
                "posts": [{"aweme_id": "1001", "desc": "first"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (user_dir / "087_first.transcribe.mp3").write_bytes(b"audio")

    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr(
        "dy_cli.commands.download.DouyinAPIClient.from_config",
        lambda account: fake_api,
    )

    result = CliRunner().invoke(download, ["SEC_UID", "--user"])

    assert result.exit_code == 0
    assert fake_api.download_url_calls == []
    assert fake_api.downloaded == []


def test_batch_user_download_skips_when_matching_plain_mp3_exists(monkeypatch, tmp_path):
    fake_api = _FakeBatchAPIClient({})
    user_dir = tmp_path / "tester"
    user_dir.mkdir()
    (user_dir / "tester_posts.json").write_text(
        json.dumps(
            {
                "sec_user_id": "SEC_UID",
                "nickname": "tester",
                "complete": True,
                "total": 1,
                "posts": [{"aweme_id": "1001", "desc": "first"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (user_dir / "087_first.mp3").write_bytes(b"audio")

    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr(
        "dy_cli.commands.download.DouyinAPIClient.from_config",
        lambda account: fake_api,
    )

    result = CliRunner().invoke(download, ["SEC_UID", "--user"])

    assert result.exit_code == 0
    assert fake_api.download_url_calls == []
    assert fake_api.downloaded == []


def test_batch_user_download_with_audio_extracts_mp3(monkeypatch, tmp_path):
    fake_api = _FakeBatchAPIClient(
        {
            0: {
                "aweme_list": [{"aweme_id": "1001", "desc": "first"}],
                "has_more": 0,
                "max_cursor": 0,
            },
        }
    )
    extract_calls = []

    def fake_extract(video_path, audio_path):
        extract_calls.append((video_path, audio_path))
        with open(audio_path, "wb") as f:
            f.write(b"audio")

    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr("dy_cli.commands.download.DouyinAPIClient.from_config", lambda account: fake_api)
    monkeypatch.setattr("dy_cli.commands.download.extract_audio", fake_extract)

    result = CliRunner().invoke(download, ["SEC_UID", "--user", "--audio"])

    assert result.exit_code == 0
    assert (tmp_path / "tester" / "001_first.mp4").exists()
    assert (tmp_path / "tester" / "001_first.mp3").exists()
    assert extract_calls == [
        (
            str(tmp_path / "tester" / "001_first.mp4"),
            str(tmp_path / "tester" / "001_first.part.mp3"),
        )
    ]


def test_batch_user_download_with_audio_delete_video_removes_mp4(monkeypatch, tmp_path):
    fake_api = _FakeBatchAPIClient(
        {
            0: {
                "aweme_list": [{"aweme_id": "1001", "desc": "first"}],
                "has_more": 0,
                "max_cursor": 0,
            },
        }
    )

    def fake_extract(video_path, audio_path):
        with open(audio_path, "wb") as f:
            f.write(b"audio")

    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr("dy_cli.commands.download.DouyinAPIClient.from_config", lambda account: fake_api)
    monkeypatch.setattr("dy_cli.commands.download.extract_audio", fake_extract)

    result = CliRunner().invoke(download, ["SEC_UID", "--user", "--audio-delete-video"])
    progress = json.loads((tmp_path / "tester" / "tester_progress.json").read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert not (tmp_path / "tester" / "001_first.mp4").exists()
    assert (tmp_path / "tester" / "001_first.mp3").exists()
    assert progress["items"]["1001"]["file"] == "001_first.mp3"


def test_batch_user_download_skips_when_matching_transcript_json_exists(monkeypatch, tmp_path):
    fake_api = _FakeBatchAPIClient({})
    user_dir = tmp_path / "tester"
    user_dir.mkdir()
    (user_dir / "tester_posts.json").write_text(
        json.dumps(
            {
                "sec_user_id": "SEC_UID",
                "nickname": "tester",
                "complete": True,
                "total": 1,
                "posts": [{"aweme_id": "1001", "desc": "first"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (user_dir / "087_first.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr(
        "dy_cli.commands.download.DouyinAPIClient.from_config",
        lambda account: fake_api,
    )

    result = CliRunner().invoke(download, ["SEC_UID", "--user"])

    assert result.exit_code == 0
    assert fake_api.download_url_calls == []
    assert fake_api.downloaded == []


def test_batch_user_download_does_not_sleep_between_consecutive_local_skips(monkeypatch, tmp_path):
    fake_api = _FakeBatchAPIClient({})
    user_dir = tmp_path / "tester"
    user_dir.mkdir()
    (user_dir / "tester_posts.json").write_text(
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
    (user_dir / "001_first.mp4").write_bytes(b"existing")
    (user_dir / "002_second.mp4").write_bytes(b"existing")
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
    assert fake_api.download_url_calls == []
    assert sleep_calls == []


def test_batch_user_download_redownloads_when_only_part_file_exists(monkeypatch, tmp_path):
    fake_api = _FakeBatchAPIClient({})
    user_dir = tmp_path / "tester"
    user_dir.mkdir()
    (user_dir / "tester_posts.json").write_text(
        json.dumps(
            {
                "sec_user_id": "SEC_UID",
                "nickname": "tester",
                "complete": True,
                "total": 1,
                "posts": [
                    {"aweme_id": "1001", "desc": "first"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (user_dir / "001_first.mp4.part").write_bytes(b"partial")

    monkeypatch.setattr(
        "dy_cli.commands.download.config.load_config",
        lambda: {"default": {"download_dir": str(tmp_path), "account": "browser"}},
    )
    monkeypatch.setattr(
        "dy_cli.commands.download.DouyinAPIClient.from_config",
        lambda account: fake_api,
    )

    result = CliRunner().invoke(download, ["SEC_UID", "--user"])
    progress = json.loads((user_dir / "tester_progress.json").read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert fake_api.download_url_calls == ["1001"]
    assert fake_api.downloaded[0][1].endswith("001_first.mp4.part")
    assert (user_dir / "001_first.mp4").exists()
    assert progress["completed"] == 1
    assert progress["items"]["1001"]["status"] == "done"


def test_download_command_source_parses_with_python_310_grammar():
    source = Path("src/dy_cli/commands/download.py").read_text(encoding="utf-8")

    parse(source, filename="download.py", feature_version=(3, 10))
