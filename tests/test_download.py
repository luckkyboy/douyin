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
    assert [item["aweme_id"] for item in json.loads(export_path.read_text(encoding="utf-8"))] == [
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


def test_download_command_source_parses_with_python_310_grammar():
    source = Path("src/dy_cli/commands/download.py").read_text(encoding="utf-8")

    parse(source, filename="download.py", feature_version=(3, 10))
