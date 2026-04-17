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
