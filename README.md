<p align="center">
  <h1 align="center">🎬 dy-cli</h1>
  <p align="center">Douyin (抖音/TikTok China) CLI — search, download, publish, trending, live, and more.</p>
</p>

<p align="center">
  <a href="https://pypi.org/project/dy-cli/"><img src="https://img.shields.io/pypi/v/dy-cli.svg" alt="PyPI"></a>
  <a href="https://github.com/Youhai020616/douyin/actions"><img src="https://github.com/Youhai020616/douyin/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/dy-cli/"><img src="https://img.shields.io/badge/python-≥3.10-blue.svg" alt="Python"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License"></a>
</p>

<p align="center">
  <a href="#install">Install</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#commands">Commands</a> •
  <a href="#features">Features</a> •
  <a href="./LICENSE">License</a>
</p>

---

<p align="center">
  <img src="./demo.gif" alt="dy-cli demo" width="800">
</p>

## Install

```bash
pip install dy-cli
```

Or from source:

```bash
git clone https://github.com/Youhai020616/douyin.git
cd douyin && bash setup.sh
```

## Quick Start

```bash
dy login                                # QR scan login (one time)
dy search "美食"                         # Search → results cached
dy read 1                               # Read 1st result (short index)
dy dl 1                                 # Download 1st result (no watermark)
dy like 1                               # Like 1st result
dy trending                             # Hot trending Top 50
dy publish -t "标题" -c "描述" -v video.mp4   # Publish video
```

## Features

- 🔍 **Search** — keyword search with sort/time/type filters, user search
- 📥 **Download** — no-watermark video/image with progress bar, supports full user archive download with local manifest cache
- 📝 **Transcribe** — extract audio from local videos and save Whisper transcripts as same-name JSON files
- 📝 **Publish** — video & image posts with tags, cover, scheduling, visibility
- 🔥 **Trending** — real-time hot search Top 50 with watch mode
- 📺 **Live** — stream info, URL extraction, ffmpeg recording
- 💬 **Interact** — like, favorite, comment, follow (Playwright)
- 📊 **Analytics** — creator dashboard via XHR interception
- 👤 **Profile** — user info, posts listing
- 🔢 **Short Index** — `dy search → dy read 1 → dy like 1 → dy dl 1`
- 📦 **Export** — `dy search "AI" -o results.csv` (JSON/CSV/YAML)
- 🔐 **Login** — QR scan + browser cookie auto-extraction
- 👥 **Multi-Account** — isolated cookie storage
- 🛡️ **Anti-Detection** — Gaussian jitter, exponential backoff, captcha cooldown

## Commands

### Search & Read

```bash
dy search "关键词"                        # Search videos
dy search "咖啡" --sort 最多点赞          # Sort by likes
dy search "风景" --type atlas             # Search photo posts
dy search "日食记" --type user            # Search users
dy search "AI" -o results.csv            # Export to CSV
dy read 1                                # Read 1st result (short index)
dy detail AWEME_ID                       # Detail by ID
dy comments 1                            # View comments (Playwright)
```

### Download

```bash
dy dl 1                                  # Download by short index
dy download https://v.douyin.com/xxx     # Download by URL
dy download 1234567890 --music           # Also download BGM
dy dl SEC_USER_ID --user                 # Full user archive download (auto-pagination)
dy dl SEC_USER_ID --user --limit 20      # Only download the first 20 posts
```

User archive download behavior:

- `dy dl SEC_USER_ID --user` automatically paginates through all posts for that account
- before downloading media, it exports a full post manifest to `<download_dir>/<nickname>/<nickname>_posts.json`
- it also writes `<download_dir>/<nickname>/<nickname>_progress.json` to persist per-`aweme_id` download state
- if that manifest exists and is marked as complete for the same `sec_user_id`, later runs reuse it instead of refetching from Douyin
- reruns resume from `failed` / `pending` items in `progress.json` instead of starting from the beginning
- existing video/image files in the target directory are skipped automatically
- existing transcript artifacts also prevent re-downloading the original video: same-name `.transcribe.mp3` or `.json` count as already processed media
- the downloader sleeps 10 seconds between posts only after it actually fetched/downloaded a remote item; direct local-file skips do not wait

### Trending & Live

```bash
dy trending                              # Top 50
dy trending --count 10 -o hot.json       # Export top 10
dy trending --watch                      # Auto-refresh every 5 min
dy live info ROOM_ID                     # Live stream info
dy live record ROOM_ID                   # Record with ffmpeg
```

### Transcribe

```bash
dy transcribe /path/to/video.mp4         # Transcribe one local video, default output .srt
dy transcribe /path/to/audio.mp3         # Transcribe one local audio file directly, default output .srt
dy transcribe /path/to/dir               # Batch-transcribe a directory of local media
dy transcribe /path/to/dir --format json # Output same-name .json instead of .srt
dy transcribe /path/to/dir --force       # Rebuild existing transcript output files
dy transcribe /path/to/dir --delete-video # Delete mp4 after successful transcription, keep mp3 + subtitle/transcript
```

Transcription behavior:

- `dy transcribe <file_or_dir>` works on already-downloaded local videos and supported local audio files
- audio is extracted with `ffmpeg` and submitted to a local Whisper ASR webservice
- direct audio inputs such as `.mp3` skip the ffmpeg extraction step and are submitted as-is
- default output is same-name `.srt`; when `--format json` is used, output becomes same-name `.json`
- directory mode writes `transcribe_progress.json` for resume support
- existing same-name output files for the selected format are treated as completed work and skipped by default
- `.part` files are used for intermediate audio and JSON output so interrupted runs are not treated as complete
- by default the original `.mp4`, extracted `.transcribe.mp3`, and transcript/subtitle output are all kept
- when `--delete-video` is provided, the original `.mp4` is removed after a successful transcription, while the `.transcribe.mp3` and `.srt/.json` are kept
- `--format json` writes structured transcript JSON with both `text_raw` and corrected `text`; you can configure `asr.replace_map` to normalize common misrecognitions

### Publish

```bash
dy publish -t "标题" -c "描述" -v video.mp4                         # Video
dy publish -t "标题" -c "描述" -i img1.jpg -i img2.jpg              # Image post
dy publish -t "标题" -v v.mp4 --tags AI --visibility 仅自己可见      # Private + tags
dy publish -t "标题" -v v.mp4 --schedule "2026-03-20T08:00:00+08:00" # Scheduled
dy pub -t "标题" -v v.mp4 --dry-run                                  # Preview only
```

### Interact

```bash
dy like 1                                # Like (short index)
dy like 1 --unlike                       # Unlike
dy fav 1                                 # Favorite
dy comment 1 -c "好看!"                  # Comment
dy follow SEC_USER_ID                    # Follow user
```

### Profile & Analytics

```bash
dy me                                    # My login info
dy profile SEC_USER_ID --posts           # User profile + posts
dy analytics                             # Creator dashboard
dy notifications                         # Messages
```

### Account & Config

```bash
dy login                                 # QR scan login
dy login --browser                       # Extract cookies from browser
dy status                                # Login status
dy account list                          # List accounts
dy config show                           # Show config
dy config set api.proxy http://...       # Set proxy
dy config set asr.whisper_webservice.base_url http://127.0.0.1:9000
dy config set asr.whisper_webservice.language zh
dy config set asr.whisper_webservice.vad_filter true
dy config set asr.replace_map '{"龙非":"龙飞"}'
```

### Aliases

| Short | Command | | Short | Command |
|-------|---------|---|-------|---------|
| `dy s` | `search` | | `dy r` | `detail` (read) |
| `dy dl` | `download` | | `dy t` | `trending` |
| `dy pub` | `publish` | | `dy fav` | `favorite` |
| `dy cfg` | `config` | | `dy acc` | `account` |

## Architecture

| Engine | Used for | Technology |
|--------|----------|------------|
| **API Client** | Search, download, trending, live, profile | httpx + reverse-engineered API |
| **Playwright** | Publish, login, analytics, like, comment | Chromium browser automation |

## Platform Support

macOS ✅ &nbsp; Linux ✅ &nbsp; Windows ✅

## License

[MIT](./LICENSE)

## 🔗 Ecosystem

| Project | Description |
|---------|-------------|
| [AgentMind](https://github.com/Youhai020616/Agentmind) | Self-learning memory system for AI agents |
| [stealth-cli](https://github.com/Youhai020616/stealth-cli) | Anti-detection browser CLI powered by Camoufox |
| [stealth-x](https://github.com/Youhai020616/stealth-x) | Stealth X/Twitter automation |
| [xiaohongshu](https://github.com/Youhai020616/xiaohongshu) | Xiaohongshu automation |
| [freepost](https://github.com/Youhai020616/freepost-saas) | AI social media management |
