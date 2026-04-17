"""
dy download — 无水印下载命令（抖音特色功能）。
"""
from __future__ import annotations

import os
import re
import time
import json
from datetime import datetime, timezone

import click
from rich.progress import BarColumn, DownloadColumn, Progress, SpinnerColumn, TextColumn, TransferSpeedColumn

from dy_cli.engines.api_client import DouyinAPIClient, DouyinAPIError
from dy_cli.engines.playwright_client import PlaywrightClient, PlaywrightError
from dy_cli.utils import config
from dy_cli.utils.index_cache import resolve_id
from dy_cli.utils.output import console, error, info, success, warning


@click.command("download", help="下载抖音视频/图片 (无水印, 支持短索引/批量)")
@click.argument("url_or_id")
@click.option("--output-dir", "-o", default=None, help="保存目录 (默认 ~/Downloads/douyin)")
@click.option("--music", is_flag=True, help="同时下载背景音乐")
@click.option("--limit", type=int, default=0, help="批量下载: 限制作品数量，默认全部 (需配合 --user)")
@click.option("--user", is_flag=True, help="批量下载该用户的全部作品 (URL_OR_ID 为 sec_user_id)")
@click.option("--account", default=None, help="使用指定账号")
@click.option("--json-output", "as_json", is_flag=True, help="仅输出下载链接 (JSON)")
def download(url_or_id, output_dir, music, limit, user, account, as_json):
    """
    下载抖音视频/图片（无水印）。支持短索引和批量下载。

    单个下载:
      dy dl 1                          (搜索后用短索引)
      dy dl https://v.douyin.com/xxx   (分享链接)
      dy dl 1234567890                 (视频 ID)

    批量下载用户作品:
      dy dl SEC_USER_ID --user             (自动翻页下载全部作品)
      dy dl SEC_USER_ID --user --limit 20 (只下载前 20 个作品)
    """
    cfg = config.load_config()
    output_dir = output_dir or cfg["default"].get("download_dir", os.path.expanduser("~/Downloads/douyin"))
    os.makedirs(output_dir, exist_ok=True)

    client = DouyinAPIClient.from_config(account)

    try:
        # 批量下载用户作品
        if user:
            _batch_download_user(client, url_or_id, output_dir, music, limit, as_json)
            return

        # Resolve aweme_id (支持短索引)
        try:
            url_or_id = resolve_id(url_or_id)
        except ValueError as e:
            error(str(e))
            raise SystemExit(1)
        if url_or_id.isdigit():
            aweme_id = url_or_id
        else:
            info("正在解析分享链接...")
            aweme_id = client.resolve_share_url(url_or_id)

        info(f"视频 ID: {aweme_id}")

        # Get download info
        info("正在获取下载链接...")
        dl_info = client.get_download_url(aweme_id)

        # 优先使用真实浏览器播放器拿到的 currentSrc。
        try:
            browser_account = account or cfg["default"].get("account", "default")
            browser_client = PlaywrightClient(account=browser_account, headless=True)
            browser_video_url = browser_client.get_video_current_src(aweme_id)
            if browser_video_url.startswith("http"):
                dl_info["video_url"] = browser_video_url
                info(f"浏览器播放器地址: {browser_video_url.split('/')[2]}")
        except PlaywrightError as e:
            warning(f"未能读取浏览器播放器地址，回退 API 链路: {e}")

        if as_json:
            from dy_cli.utils.output import print_json
            print_json(dl_info)
            return

        desc = dl_info.get("desc", "untitled")
        author = dl_info.get("author", "unknown")

        # Sanitize filename
        safe_name = re.sub(r'[\\/:*?"<>|\n\r]', '_', desc)[:50].strip('_') or aweme_id
        prefix = f"{author}_{safe_name}"

        downloaded_files = []

        # Download video
        video_url = dl_info.get("video_url")
        if video_url:
            video_path = os.path.join(output_dir, f"{prefix}.mp4")
            info("正在下载视频...")
            _download_with_progress(client, video_url, video_path)
            downloaded_files.append(video_path)

        # Download images (for image posts)
        image_urls = dl_info.get("images")
        if image_urls:
            for idx, img_url in enumerate(image_urls, 1):
                img_path = os.path.join(output_dir, f"{prefix}_{idx}.jpg")
                info(f"正在下载图片 {idx}/{len(image_urls)}...")
                _download_with_progress(client, img_url, img_path)
                downloaded_files.append(img_path)

        # Download music
        if music:
            music_url = dl_info.get("music_url")
            if music_url:
                music_path = os.path.join(output_dir, f"{prefix}_music.mp3")
                info("正在下载音乐...")
                _download_with_progress(client, music_url, music_path)
                downloaded_files.append(music_path)
            else:
                warning("未找到背景音乐")

        # Summary
        if downloaded_files:
            console.print()
            success(f"下载完成! ({len(downloaded_files)} 个文件)")
            for f in downloaded_files:
                size = os.path.getsize(f)
                size_str = f"{size / 1024 / 1024:.1f}MB" if size > 1024 * 1024 else f"{size / 1024:.0f}KB"
                console.print(f"  📁 {f} ({size_str})")
        else:
            warning("未找到可下载的内容")

    except DouyinAPIError as e:
        error(f"下载失败: {e}")
        raise SystemExit(1)
    finally:
        client.close()


def _batch_download_user(
    client: DouyinAPIClient,
    sec_user_id: str,
    output_dir: str,
    music: bool,
    limit: int,
    as_json: bool,
):
    """批量下载用户作品。"""
    limit_desc = "all" if limit <= 0 else str(limit)
    info(f"正在获取用户作品列表 (limit={limit_desc})...")
    try:
        profile = client.get_user_profile(sec_user_id)
        nickname = profile.get("nickname", sec_user_id)
        info(f"用户: {nickname}")
    except Exception:
        nickname = sec_user_id

    safe_nickname = re.sub(r'[\\/:*?"<>|\n\r]', '_', nickname)
    user_dir = os.path.join(output_dir, safe_nickname)
    os.makedirs(user_dir, exist_ok=True)

    export_path = os.path.join(user_dir, f"{safe_nickname}_posts.json")
    progress_path = os.path.join(user_dir, f"{safe_nickname}_progress.json")
    aweme_list = _load_cached_posts(export_path, sec_user_id)

    if aweme_list is None:
        aweme_list = _fetch_user_posts(client, sec_user_id, limit)
        if not aweme_list:
            warning("未找到作品")
            return

        info("正在导出作品列表...")
        _export_posts_manifest(export_path, sec_user_id, nickname, aweme_list)
    else:
        info(f"复用本地作品缓存: {export_path}")

    info(f"找到 {len(aweme_list)} 个作品，开始下载...")
    downloaded = 0

    target_posts = aweme_list if limit <= 0 else aweme_list[:limit]
    progress = _load_progress(progress_path, sec_user_id, export_path, len(target_posts), target_posts)

    for i, aweme in enumerate(target_posts, 1):
        aweme_id = aweme.get("aweme_id", "")
        desc = aweme.get("desc", "untitled")
        safe = re.sub(r'[\\/:*?"<>|\n\r]', '_', desc)[:40].strip('_') or aweme_id
        video_path = os.path.join(user_dir, f"{i:03d}_{safe}.mp4")
        item_progress = progress["items"].setdefault(aweme_id, {"status": "pending"})
        should_sleep = False

        if _media_exists(video_path, user_dir, i, safe):
            info(f"[{i}/{len(target_posts)}] 本地文件已存在，跳过: {safe[:30]}")
            _mark_progress(progress, progress_path, aweme_id, i, "done", file=os.path.basename(video_path))
            continue

        try:
            dl_info = client.get_download_url(aweme_id)
            should_sleep = True
            video_url = dl_info.get("video_url")
            if video_url:
                if os.path.exists(video_path):
                    info(f"[{i}/{len(target_posts)}] 已存在，跳过: {safe[:30]}")
                    item_progress["file"] = os.path.basename(video_path)
                else:
                    info(f"[{i}/{len(target_posts)}] {safe[:30]}...")
                    _download_with_progress(client, video_url, video_path)
                    downloaded += 1
                    item_progress["file"] = os.path.basename(video_path)

            # Images
            images = dl_info.get("images")
            if images:
                for idx, img_url in enumerate(images, 1):
                    path = os.path.join(user_dir, f"{i:03d}_{safe}_{idx}.jpg")
                    if os.path.exists(path):
                        info(f"[{i}/{len(target_posts)}] 图片已存在，跳过: {os.path.basename(path)}")
                        continue
                    _download_atomically(client, img_url, path)
                downloaded += 1
            _mark_progress(progress, progress_path, aweme_id, i, "done", file=item_progress.get("file"))
        except Exception as e:
            warning(f"[{i}] 下载失败: {e}")
            _mark_progress(progress, progress_path, aweme_id, i, "failed", error=str(e), file=item_progress.get("file"))
        finally:
            if should_sleep and i < len(target_posts):
                info("等待 10 秒后继续，降低风控风险...")
                time.sleep(10)

    console.print()
    success(f"批量下载完成! {downloaded}/{len(target_posts)} 个作品")
    console.print(f"  📁 {user_dir}")


def _fetch_user_posts(
    client: DouyinAPIClient,
    sec_user_id: str,
    limit: int,
) -> list[dict]:
    """翻页获取用户作品列表。limit<=0 表示抓取全部。"""
    aweme_list: list[dict] = []
    max_cursor = 0
    page_size = 20 if limit <= 0 else min(limit, 20)

    while True:
        posts = client.get_user_posts(sec_user_id, max_cursor=max_cursor, count=page_size)
        page_items = posts.get("aweme_list", [])
        if not page_items:
            break

        aweme_list.extend(page_items)

        if limit > 0 and len(aweme_list) >= limit:
            return aweme_list[:limit]

        if not posts.get("has_more"):
            break

        next_cursor = posts.get("max_cursor", max_cursor)
        if next_cursor == max_cursor:
            warning("分页游标未推进，提前停止以避免死循环")
            break
        max_cursor = next_cursor

    return aweme_list


def _load_cached_posts(export_path: str, sec_user_id: str) -> list[dict] | None:
    """加载有效的全量作品缓存。"""
    if not os.path.exists(export_path):
        return None

    try:
        with open(export_path, encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        warning(f"作品缓存读取失败，重新拉取: {e}")
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get("sec_user_id") != sec_user_id:
        return None
    if payload.get("complete") is not True:
        return None

    posts = payload.get("posts", [])
    if not isinstance(posts, list):
        return None
    return posts


def _export_posts_manifest(export_path: str, sec_user_id: str, nickname: str, posts: list[dict]) -> None:
    """导出带元信息的全量作品缓存。"""
    payload = {
        "sec_user_id": sec_user_id,
        "nickname": nickname,
        "complete": True,
        "total": len(posts),
        "posts": posts,
    }
    os.makedirs(os.path.dirname(export_path) or ".", exist_ok=True)
    with open(export_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    success(f"已导出 {len(posts)} 条到 {export_path}")


def _load_progress(
    progress_path: str,
    sec_user_id: str,
    export_path: str,
    total: int,
    posts: list[dict],
) -> dict:
    """加载或初始化下载进度。"""
    items = {post.get("aweme_id", ""): {"status": "pending"} for post in posts if post.get("aweme_id")}
    payload = {
        "sec_user_id": sec_user_id,
        "manifest_file": os.path.basename(export_path),
        "total": total,
        "completed": 0,
        "last_index": 0,
        "last_aweme_id": "",
        "updated_at": "",
        "items": items,
    }

    if os.path.exists(progress_path):
        try:
            with open(progress_path, encoding="utf-8") as f:
                existing = json.load(f)
            if isinstance(existing, dict) and existing.get("sec_user_id") == sec_user_id:
                payload.update({k: v for k, v in existing.items() if k != "items"})
                existing_items = existing.get("items", {})
                if isinstance(existing_items, dict):
                    for aweme_id, state in existing_items.items():
                        if aweme_id in items and isinstance(state, dict):
                            items[aweme_id].update(state)
        except (OSError, json.JSONDecodeError):
            warning("进度文件读取失败，重新初始化")

    payload["items"] = items
    payload["total"] = total
    _save_progress(progress_path, payload)
    return payload


def _save_progress(progress_path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(progress_path) or ".", exist_ok=True)
    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _mark_progress(
    progress: dict,
    progress_path: str,
    aweme_id: str,
    index: int,
    status: str,
    *,
    file: str | None = None,
    error: str | None = None,
) -> None:
    item = progress["items"].setdefault(aweme_id, {})
    item["status"] = status
    if file:
        item["file"] = file
    if error:
        item["error"] = error
    else:
        item.pop("error", None)

    progress["completed"] = sum(1 for state in progress["items"].values() if state.get("status") == "done")
    progress["last_index"] = index
    progress["last_aweme_id"] = aweme_id
    progress["updated_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    _save_progress(progress_path, progress)


def _media_exists(video_path: str, user_dir: str, index: int, safe: str) -> bool:
    if os.path.exists(video_path):
        return True
    normalized_video_name = _strip_numeric_prefix(os.path.basename(video_path))
    normalized_mp3_name = f"{safe}.transcribe.mp3"
    normalized_json_name = f"{safe}.json"
    image_prefix = f"{safe}_"
    for name in os.listdir(user_dir):
        normalized_name = _strip_numeric_prefix(name)
        if normalized_name == normalized_video_name:
            return True
        if normalized_name == normalized_mp3_name:
            return True
        if normalized_name == normalized_json_name:
            return True
        if normalized_name.startswith(image_prefix):
            return True
    return False


def _strip_numeric_prefix(filename: str) -> str:
    return re.sub(r"^\d+_", "", filename)


def _download_with_progress(client: DouyinAPIClient, url: str, output_path: str):
    """带进度条的下载。"""
    temp_path = f"{output_path}.part"
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(os.path.basename(output_path), total=None)

        def on_progress(downloaded: int, total: int):
            if total > 0:
                progress.update(task, total=total, completed=downloaded)
            else:
                progress.update(task, completed=downloaded)

        client.download_file(url, temp_path, progress_callback=on_progress)
    os.replace(temp_path, output_path)


def _download_atomically(client: DouyinAPIClient, url: str, output_path: str):
    """先写入 .part，完成后再原子重命名。"""
    temp_path = f"{output_path}.part"
    client.download_file(url, temp_path)
    os.replace(temp_path, output_path)
