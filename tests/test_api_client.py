import json

from dy_cli.engines.api_client import DouyinAPIClient
from dy_cli.utils import config


class TestDouyinAPIClientCookies:
    def test_loads_playwright_storage_state_into_cookie_jar(self, tmp_path, monkeypatch):
        cfg_dir = str(tmp_path / ".dy")
        monkeypatch.setattr(config, "CONFIG_DIR", cfg_dir)
        monkeypatch.setattr(config, "CONFIG_FILE", str(tmp_path / ".dy" / "config.json"))
        monkeypatch.setattr(config, "COOKIES_DIR", str(tmp_path / ".dy" / "cookies"))

        cookie_file = config.get_cookie_file("work")
        with open(cookie_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "cookies": [
                        {"name": "sessionid", "value": "abc", "domain": ".douyin.com", "path": "/"},
                        {"name": "ttwid", "value": "xyz", "domain": ".douyin.com", "path": "/"},
                    ],
                    "origins": [],
                },
                f,
            )

        client = DouyinAPIClient(account="work")

        assert client._get_cookie_string() == "sessionid=abc; ttwid=xyz"

    def test_save_cookies_persists_cookie_jar_to_account_file(self, tmp_path, monkeypatch):
        cfg_dir = str(tmp_path / ".dy")
        monkeypatch.setattr(config, "CONFIG_DIR", cfg_dir)
        monkeypatch.setattr(config, "CONFIG_FILE", str(tmp_path / ".dy" / "config.json"))
        monkeypatch.setattr(config, "COOKIES_DIR", str(tmp_path / ".dy" / "cookies"))

        client = DouyinAPIClient(account="writer", cookie="sessionid=abc; ttwid=xyz")

        client._save_cookies()

        with open(config.get_cookie_file("writer"), encoding="utf-8") as f:
            saved = json.load(f)

        assert saved["origins"] == []
        assert saved["cookies"] == [
            {"name": "sessionid", "value": "abc", "domain": ".douyin.com", "path": "/", "secure": False},
            {"name": "ttwid", "value": "xyz", "domain": ".douyin.com", "path": "/", "secure": False},
        ]
