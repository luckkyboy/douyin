# 🎬 dy-cli 使用指南

抖音命令行工具 — 一条命令搞定搜索、下载、发布、互动、热榜、直播、数据分析。

## 安装

### 前提条件

- Python 3.10+
- Playwright Chromium (setup.sh 会自动安装)
- ffmpeg (可选，直播录制需要: `brew install ffmpeg`)

### 一键安装

```bash
git clone https://github.com/your-username/douyin.git
cd douyin
bash setup.sh
```

`setup.sh` 会自动完成:
- ✅ 检测 Python 版本
- ✅ 创建虚拟环境 `.venv`
- ✅ 安装所有依赖 (`httpx`, `playwright`, `click`, `rich`)
- ✅ 安装 Playwright Chromium
- ✅ 注册 `dy` 命令
- ✅ 生成 `activate.sh` 快捷激活脚本

### 手动安装

```bash
git clone https://github.com/your-username/douyin.git
cd douyin
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
dy --version
```

## 快速开始

### 首次使用

```bash
source activate.sh
dy init
```

`dy init` 引导你完成:
1. ✅ 环境检查 (Python, Playwright, httpx)
2. ✅ 安装 Playwright Chromium
3. ✅ 配置代理 (国内直接回车跳过)
4. ✅ 扫码登录抖音

### 以后每次使用

```bash
source activate.sh
dy search "关键词"
```

---

## 命令详解

### 搜索

```bash
dy search "AI创业"                        # 综合搜索
dy search "咖啡" --sort 最多点赞          # 按点赞排序
dy search "春招" --time 一天内            # 限制时间
dy search "科技" --type video             # 仅视频
dy search "风景" --type atlas             # 仅图文
dy search "科技" --count 50              # 返回 50 条
dy search "科技" --json-output           # JSON 输出
```

### 下载

```bash
dy download https://v.douyin.com/xxxxx/   # 分享链接
dy download 1234567890                     # 视频 ID
dy download URL --music                    # 同时下载 BGM
dy download URL --audio                    # 下载后额外提取同名 mp3
dy download URL --audio-delete-video       # 下载后提取 mp3，并删除 mp4
dy download URL -o ~/Videos/douyin         # 指定目录
dy download URL --json-output              # 仅输出链接
dy dl SEC_USER_ID --user                   # 自动翻页下载账号全部作品
dy dl SEC_USER_ID --user --limit 20        # 只下载前 20 个作品
```

批量下载账号作品时，当前逻辑为：

- 首次执行 `dy dl SEC_USER_ID --user` 时，会自动分页拉取该账号全部作品
- 在下载目录下生成 `<nickname>/<nickname>_posts.json`，其中包含 `sec_user_id`、`complete`、`total` 和完整 `posts` 列表
- 同时生成 `<nickname>/<nickname>_progress.json`，按 `aweme_id` 记录 `done/failed/pending` 下载状态
- 如果后续再次执行同一个账号的全量下载，并且本地 `posts.json` 已存在且标记为完整，会直接复用该缓存，不再重新请求作品列表
- 再次执行时，会优先读取 `progress.json`，从未完成或失败的作品继续下载，而不是从头开始
- 下载阶段如果目标视频或图片文件已存在，会自动跳过
- 如果目录里已经存在同名 `.mp3`、`.transcribe.mp3` 或同名转写 `.json`，也会把该原视频视为已处理，直接跳过下载
- 如果指定 `--audio`，视频下载完成后会立即提取同名 `.mp3`，但保留 `.mp4`
- 如果指定 `--audio-delete-video`，则提取同名 `.mp3` 后删除下载好的 `.mp4`
- 只有在当前作品确实发起了远端请求/下载后，才会在作品之间等待 10 秒；本地直接跳过不会额外等待

### 转写

```bash
dy transcribe /path/to/video.mp4         # 转写单个本地视频，默认输出 srt
dy transcribe /path/to/audio.mp3         # 直接转写单个本地音频文件，默认输出 srt
dy transcribe /path/to/dir               # 批量转写目录下的本地音视频
dy transcribe /path/to/dir --format json # 输出同名 json 而不是 srt
dy transcribe /path/to/dir --force       # 即使已有同名输出文件也重新转写
dy transcribe /path/to/dir --delete-video # 转写成功后删除原 mp4，保留 mp3 和 srt/json
```

批量转写本地音视频时，当前逻辑为：

- 仅处理已经下载到本地的音视频文件，不会自动下载视频
- 视频先使用 `ffmpeg` 提取音频，再调用本地 Whisper Webservice
- 如果同目录下已经存在同 basename 的音频文件，例如 `demo.mp3` 对应 `demo.mp4`，则直接复用该音频，不再重复抽取
- 默认输出同名 `.srt`；如果指定 `--format json`，则输出同名 `.json`
- 目录模式下会生成 `transcribe_progress.json`，用于记录 `done/failed/pending` 状态
- 直接传入 `.mp3/.m4a/.wav/.aac/.flac/.ogg` 等音频文件时，不再调用 `ffmpeg` 抽取音频
- 如果当前格式对应的同名输出文件已存在，默认直接跳过，并视为该文件已完成转写
- 使用 `.part` 临时文件写中间音频和结果文件，避免中断后把半截文件误判为成功
- 默认不删除任何文件，原视频 `.mp4`、提取出的 `.transcribe.mp3` 和转写结果 `.srt/.json` 都保留
- 如果加上 `--delete-video`，则在转写成功后删除原 `.mp4`，但继续保留 `.transcribe.mp3` 和 `.srt/.json`

### 发布

```bash
# 视频发布
dy publish -t "标题" -c "描述" -v video.mp4

# 图文发布
dy publish -t "标题" -c "描述" -i img1.jpg -i img2.jpg

# 完整选项
dy publish -t "旅行日记" -c "巴厘岛真美" \
  -v trip.mp4 \
  --tags 旅行 --tags 巴厘岛 \
  --visibility 公开 \
  --schedule "2026-03-16T08:00:00+08:00" \
  --thumbnail cover.jpg

# 预览
dy publish -t "测试" -c "测试" -v test.mp4 --dry-run

# 从文件读取描述
dy publish -t "深度文章" --content-file desc.txt -v video.mp4
```

### 热榜

```bash
dy trending                              # 显示 Top 50
dy trending --count 20                   # 显示 Top 20
dy trending --watch                      # 每 5 分钟刷新
dy trending --json-output                # JSON 输出
```

### 直播

```bash
dy live info ROOM_ID                     # 直播间信息
dy live record ROOM_ID                   # 录制直播 (需要 ffmpeg)
dy live record ROOM_ID --quality HD1     # 指定画质
dy live record ROOM_ID -o live.mp4       # 指定输出文件
```

### 互动

```bash
dy like AWEME_ID                         # 点赞
dy favorite AWEME_ID                     # 收藏
dy comment AWEME_ID -c "写得好!"         # 评论
dy follow SEC_USER_ID                    # 关注
dy comments AWEME_ID                     # 查看评论
dy comments AWEME_ID --count 50          # 更多评论
```

### 用户

```bash
dy me                                    # 我的信息
dy profile SEC_USER_ID                   # 用户主页
dy profile SEC_USER_ID --posts           # 含作品列表
```

### 数据看板

```bash
dy analytics                             # 数据看板
dy analytics --csv data.csv              # 导出 CSV
dy notifications                         # 通知消息
```

### 多账号

```bash
dy account list                          # 列出账号
dy account add work                      # 添加并登录
dy account default work                  # 设为默认
dy account remove work                   # 删除
dy login --account work                  # 指定账号登录
```

### 配置

```bash
dy config show                           # 查看全部
dy config set api.proxy http://...       # 设置代理
dy config set api.timeout 60             # 请求超时
dy config set playwright.headless true   # 无头模式
dy config set default.download_dir ~/Vid # 下载目录
dy config set asr.provider whisper_webservice
dy config set asr.whisper_webservice.base_url http://127.0.0.1:9000
dy config set asr.whisper_webservice.language zh
dy config set asr.whisper_webservice.vad_filter true
dy config set asr.provider tencent_asr
dy config set asr.tencent_asr.secret_id AKID...
dy config set asr.tencent_asr.secret_key ...
dy config set asr.tencent_asr.region ap-shanghai
dy config set asr.tencent_asr.engine_model_type 16k_zh
dy config set asr.replace_map '{"龙非":"龙飞"}'
dy config get api.proxy                  # 获取单项
dy config reset                          # 重置默认
```

---

## 命令别名

| 别名 | 完整命令 |
|------|---------|
| `dy pub` | `dy publish` |
| `dy s` | `dy search` |
| `dy dl` | `dy download` |
| `dy t` | `dy trending` |
| `dy fav` | `dy favorite` |
| `dy noti` | `dy notifications` |
| `dy stat` | `dy status` |
| `dy acc` | `dy account` |
| `dy cfg` | `dy config` |

---

## 引擎说明

| 引擎 | 功能 | 速度 |
|------|------|------|
| **API** | 搜索、下载、评论、热榜、直播、用户 | ⚡ 快 |
| **Playwright** | 发布、登录、数据看板、通知 | 🐢 较慢 (需浏览器) |

命令自动选择最优引擎，无需手动指定。

---

## 常见问题

### Q: 搜索返回空结果?
可能是签名算法问题。尝试先登录：
```bash
dy login
dy search "关键词"
```

### Q: 发布失败?
1. 确保已登录: `dy status`
2. Cookie 过期需重新登录: `dy login`
3. 抖音创作者中心 UI 可能更新，需要更新脚本

### Q: 如何设置代理?
```bash
dy config set api.proxy http://127.0.0.1:7897
```

### Q: 直播录制需要什么?
安装 ffmpeg:
```bash
brew install ffmpeg       # macOS
apt install ffmpeg         # Ubuntu
```
