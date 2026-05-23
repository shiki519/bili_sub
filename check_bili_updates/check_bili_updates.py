from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

import yaml

PLAYLIST_ITEMS = "1-5"
MAX_SEEN_PER_UP = 200
VIDEO_PAGE_URL_TEMPLATE = "https://space.bilibili.com/{mid}/video"
VIDEO_URL_TEMPLATE = "https://www.bilibili.com/video/{bvid}"
DYNAMIC_API_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
DYNAMIC_API_FEATURES = ",".join(
    [
        "itemOpusStyle",
        "listOnlyfans",
        "opusBigCover",
        "onlyfansVote",
        "decorationCard",
        "forwardListHidden",
        "ugcDelete",
        "onlyfansQaCard",
        "commentsNewVersion",
        "onlyfansAssetsV2",
    ]
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "up_list.yaml"
SEEN_PATH = BASE_DIR / "seen_videos.json"
UPDATES_PATH = BASE_DIR / "updates.md"
COOKIE_PATH = BASE_DIR / "bilibili.txt"

SEEN_VIDEO_DEFAULTS = {
    "bvid": "",
    "title": "",
    "url": "",
    "published_at": "",
    "up_name": "",
    "first_seen_at": "",
}


def safe_console_text(value: Any) -> str:
    text = str(value)
    if os.name != "nt":
        return text
    return text.encode("gbk", errors="replace").decode("gbk")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check recent Bilibili UP uploads with yt-dlp.")
    parser.add_argument(
        "--reset-seen",
        action="store_true",
        help="Clear seen_videos.json in memory before checking for updates.",
    )
    return parser.parse_args()


def load_up_list(config_path: Path) -> list[dict[str, str]]:
    if not config_path.exists():
        raise FileNotFoundError(f"config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    ups = data.get("ups")
    if not isinstance(ups, list) or not ups:
        raise ValueError(f"no valid ups found in {config_path}")

    normalized: list[dict[str, str]] = []
    for item in ups:
        if not isinstance(item, dict):
            continue

        name = str(item.get("name", "")).strip()
        mid = str(item.get("mid", "")).strip()
        if not name or not mid:
            continue

        normalized.append({"name": name, "mid": mid})

    if not normalized:
        raise ValueError(f"no usable up entries found in {config_path}")

    return normalized


def current_time_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_seen_video_item(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        bvid = item.strip()
        if not bvid:
            return None

        return {
            **SEEN_VIDEO_DEFAULTS,
            "bvid": bvid,
            "url": build_video_url(bvid),
        }

    if not isinstance(item, dict):
        return None

    bvid = str(item.get("bvid") or "").strip()
    if not bvid:
        return None

    normalized = dict(item)
    for key, default_value in SEEN_VIDEO_DEFAULTS.items():
        value = normalized.get(key, default_value)
        normalized[key] = str(value if value is not None else default_value)

    normalized["bvid"] = bvid
    normalized["url"] = normalized["url"] or build_video_url(bvid)
    return normalized


def merge_seen_video_metadata(
    newer_item: dict[str, Any],
    existing_item: dict[str, Any] | None,
) -> dict[str, Any]:
    if existing_item is None:
        return newer_item

    merged = dict(existing_item)
    for key, value in newer_item.items():
        if value in (None, ""):
            continue
        if key in {"title", "url", "published_at", "first_seen_at"} and existing_item.get(key):
            continue
        merged[key] = value

    return merged


def load_seen_videos(seen_path: Path) -> dict[str, list[dict[str, Any]]]:
    if not seen_path.exists():
        return {}

    try:
        with seen_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        print(safe_console_text(f"[WARN] failed to read seen history, starting fresh: {exc}"))
        return {}

    if not isinstance(data, dict):
        return {}

    normalized: dict[str, list[dict[str, Any]]] = {}
    for mid, items in data.items():
        if not isinstance(items, list):
            continue

        normalized_items: list[dict[str, Any]] = []
        for item in items:
            normalized_item = normalize_seen_video_item(item)
            if normalized_item is not None:
                normalized_items.append(normalized_item)

        normalized[str(mid)] = normalized_items
    return normalized


def save_seen_videos(seen_path: Path, seen_data: dict[str, list[dict[str, Any]]]) -> None:
    with seen_path.open("w", encoding="utf-8") as handle:
        json.dump(seen_data, handle, ensure_ascii=False, indent=2)


def build_video_page_url(mid: str) -> str:
    return VIDEO_PAGE_URL_TEMPLATE.format(mid=mid)


def build_video_url(bvid: str) -> str:
    return VIDEO_URL_TEMPLATE.format(bvid=bvid)


def normalize_video_url(bvid: str, raw_url: str) -> str:
    raw_url = str(raw_url or "").strip()
    if raw_url.startswith("//"):
        return f"https:{raw_url}"
    if raw_url.startswith("http://") or raw_url.startswith("https://"):
        return raw_url
    return build_video_url(bvid)


def merge_video_candidates(videos: list[dict[str, str]], extra_videos: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen_bvids: set[str] = set()

    for video in videos + extra_videos:
        bvid = video.get("bvid", "")
        if not bvid or bvid in seen_bvids:
            continue
        merged.append(video)
        seen_bvids.add(bvid)

    return merged


def build_cookie_args() -> list[str]:
    if COOKIE_PATH.exists():
        return ["--cookies", str(COOKIE_PATH)]
    return []


def build_cookie_opener() -> Any:
    cookie_jar = http.cookiejar.MozillaCookieJar()
    if COOKIE_PATH.exists():
        try:
            cookie_jar.load(str(COOKIE_PATH), ignore_discard=True, ignore_expires=True)
        except (http.cookiejar.LoadError, OSError) as exc:
            print(safe_console_text(f"[WARN] failed to load cookies for Bilibili API: {exc}"))

    return build_opener(HTTPCookieProcessor(cookie_jar))


def download_json(url: str, referer: str, timeout: int = 30) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": referer,
            "User-Agent": USER_AGENT,
        },
    )

    try:
        with build_cookie_opener().open(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raise RuntimeError(f"Bilibili API HTTP {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"Bilibili API request failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"Bilibili API timed out after {timeout}s") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Bilibili API returned invalid JSON: {raw[:120]}") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Bilibili API returned non-object JSON")
    if data.get("code") not in (0, None):
        raise RuntimeError(f"Bilibili API error {data.get('code')}: {data.get('message')}")
    return data


def raise_for_ytdlp_failure(result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode == 0:
        return

    stderr = (result.stderr or "").strip()
    stdout = (result.stdout or "").strip()
    combined = "\n".join(part for part in [stderr, stdout] if part)

    if "No module named yt_dlp" in combined:
        raise RuntimeError("yt-dlp is not installed. Please run: pip install -U yt-dlp")

    raise RuntimeError(combined or f"yt-dlp exited with code {result.returncode}")


def run_ytdlp_json_command(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("yt-dlp is not installed. Please run: pip install -U yt-dlp") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"yt-dlp timed out after {exc.timeout}s") from exc

    raise_for_ytdlp_failure(result)
    return result


def parse_last_json_object(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise ValueError("no valid JSON object found in yt-dlp output")


def fetch_latest_videos_with_ytdlp(mid: str, fallback_name: str) -> list[dict[str, str]]:
    url = build_video_page_url(mid)
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--flat-playlist",
        "--playlist-items",
        PLAYLIST_ITEMS,
        "--dump-json",
        *build_cookie_args(),
        url,
    ]

    result = run_ytdlp_json_command(cmd, timeout=90)

    videos: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue

        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            print(safe_console_text(f"[WARN] skipped invalid yt-dlp json line for {fallback_name} ({mid})"))
            continue

        bvid = str(item.get("id", "")).strip()
        if not bvid:
            continue

        raw_url = item.get("webpage_url") or item.get("url") or ""
        video_url = normalize_video_url(bvid, str(raw_url))

        videos.append(
            {
                "title": bvid,
                "url": video_url,
                "published_at": "",
                "description": "",
                "bvid": bvid,
                "up_name": fallback_name,
            }
        )

    return videos


def format_published_at(timestamp_value: Any, upload_date_value: Any) -> str:
    if timestamp_value not in (None, ""):
        try:
            return datetime.fromtimestamp(int(timestamp_value)).strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError, OSError):
            pass

    upload_date = str(upload_date_value or "").strip()
    if len(upload_date) == 8 and upload_date.isdigit():
        return f"{upload_date[0:4]}-{upload_date[4:6]}-{upload_date[6:8]}"

    return ""


def extract_dynamic_archive_video(item: dict[str, Any], fallback_name: str) -> dict[str, str] | None:
    modules = item.get("modules")
    if not isinstance(modules, dict):
        return None

    module_dynamic = modules.get("module_dynamic")
    if not isinstance(module_dynamic, dict):
        return None

    major = module_dynamic.get("major")
    if not isinstance(major, dict):
        return None

    archive = major.get("archive")
    if not isinstance(archive, dict):
        return None

    bvid = str(archive.get("bvid") or "").strip()
    if not bvid:
        return None

    author = modules.get("module_author")
    if not isinstance(author, dict):
        author = {}

    title = str(archive.get("title") or bvid).strip()
    description = str(archive.get("desc") or "").strip()
    raw_url = str(archive.get("jump_url") or "")
    published_at = format_published_at(author.get("pub_ts"), None)
    up_name = str(author.get("name") or fallback_name).strip() or fallback_name

    return {
        "title": title,
        "url": normalize_video_url(bvid, raw_url),
        "published_at": published_at,
        "description": description,
        "bvid": bvid,
        "up_name": up_name,
    }


def iter_dynamic_items_with_orig(items: list[Any]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        expanded.append(item)
        orig = item.get("orig")
        if isinstance(orig, dict):
            expanded.append(orig)
    return expanded


def fetch_latest_dynamic_videos(mid: str, fallback_name: str) -> list[dict[str, str]]:
    params = urlencode(
        {
            "host_mid": mid,
            "timezone_offset": "-480",
            "features": DYNAMIC_API_FEATURES,
        }
    )
    url = f"{DYNAMIC_API_URL}?{params}"
    referer = f"https://space.bilibili.com/{mid}/dynamic"
    data = download_json(url, referer=referer, timeout=30)

    payload = data.get("data")
    if not isinstance(payload, dict):
        return []

    items = payload.get("items")
    if not isinstance(items, list):
        return []

    videos: list[dict[str, str]] = []
    for item in iter_dynamic_items_with_orig(items):
        video = extract_dynamic_archive_video(item, fallback_name)
        if video is not None:
            videos.append(video)

    return videos


def fetch_latest_videos(mid: str, fallback_name: str) -> list[dict[str, str]]:
    videos = fetch_latest_videos_with_ytdlp(mid, fallback_name)
    try:
        dynamic_videos = fetch_latest_dynamic_videos(mid, fallback_name)
    except Exception as exc:
        print(safe_console_text(f"[WARN] failed to fetch dynamic videos for {fallback_name} ({mid}): {exc}"))
        dynamic_videos = []

    return merge_video_candidates(videos, dynamic_videos)


def build_detail_fallback(bvid: str, fallback_url: str, fallback_up_name: str) -> dict[str, str]:
    return {
        "title": f"未知标题（{bvid}）",
        "description": "",
        "url": fallback_url or build_video_url(bvid),
        "published_at": "",
        "bvid": bvid,
        "up_name": fallback_up_name,
    }


def fetch_video_detail_with_ytdlp(
    bvid: str,
    fallback_url: str,
    fallback_up_name: str,
) -> dict[str, str]:
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--dump-json",
        *build_cookie_args(),
        build_video_url(bvid),
    ]

    try:
        result = run_ytdlp_json_command(cmd, timeout=90)
        data = parse_last_json_object(result.stdout)
        title = str(data.get("title") or f"未知标题（{bvid}）").strip()
        description = str(data.get("description") or "")
        url = str(data.get("webpage_url") or fallback_url or build_video_url(bvid)).strip()
        up_name = str(data.get("uploader") or fallback_up_name).strip() or fallback_up_name
        published_at = format_published_at(data.get("timestamp"), data.get("upload_date"))

        return {
            "title": title,
            "description": description,
            "url": url,
            "published_at": published_at,
            "bvid": bvid,
            "up_name": up_name,
        }
    except Exception as exc:
        print(safe_console_text(f"[WARN] failed to fetch detail for {bvid}: {exc}"))
        return build_detail_fallback(bvid, fallback_url, fallback_up_name)


def merge_seen(existing_items: list[dict[str, Any]], new_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_set: set[str] = set()
    existing_by_bvid: dict[str, dict[str, Any]] = {}

    for raw_existing_item in existing_items:
        existing_item = normalize_seen_video_item(raw_existing_item)
        if existing_item is not None:
            existing_by_bvid[existing_item["bvid"]] = existing_item

    for raw_item in new_items + existing_items:
        item = normalize_seen_video_item(raw_item)
        if item is None:
            continue

        bvid = item["bvid"]
        if bvid and bvid not in seen_set:
            item = merge_seen_video_metadata(item, existing_by_bvid.get(bvid))
            merged.append(item)
            seen_set.add(bvid)
        if len(merged) >= MAX_SEEN_PER_UP:
            break

    return merged


def write_updates(
    updates_path: Path,
    new_videos: list[dict[str, str]],
    failed_ups: list[dict[str, str]],
) -> None:
    check_time = current_time_str()
    lines = [
        "# B站 UP 主更新检查",
        "",
        f"检查时间：{check_time}",
        "",
    ]

    if new_videos:
        lines.append(f"本次发现 {len(new_videos)} 个新视频。")
    else:
        lines.append("本次没有发现新视频。")

    lines.append("")

    if new_videos:
        for video in new_videos:
            lines.extend(
                [
                    f"## {video['title']}",
                    "",
                    f"- UP主：{video['up_name']}",
                    f"- 发布时间：{video['published_at']}" if video.get("published_at") else "- 发布时间：未知",
                    f"- 链接：{video['url']}",
                    f"- BVID：{video['bvid']}",
                    "",
                ]
            )

            if video.get("description", "").strip():
                lines.append("简介：")
                lines.append("")
                lines.append(video["description"].strip())
                lines.append("")

    if failed_ups:
        lines.append("## 检查失败的 UP 主")
        lines.append("")
        for item in failed_ups:
            lines.append(f"- {item['name']} ({item['mid']}): {item['reason']}")
        lines.append("")

    updates_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()

    try:
        ups = load_up_list(CONFIG_PATH)
    except Exception as exc:
        print(safe_console_text(f"[ERROR] {exc}"))
        return 1

    if args.reset_seen:
        seen_data: dict[str, list[dict[str, Any]]] = {}
        print(safe_console_text(f"[INFO] reset seen history for this run: {SEEN_PATH}"))
    else:
        seen_data = load_seen_videos(SEEN_PATH)

    new_videos: list[dict[str, str]] = []
    failed_ups: list[dict[str, str]] = []

    for up in ups:
        name = up["name"]
        mid = up["mid"]
        print(safe_console_text(f"Checking {name} ({mid}) ..."))

        new_seen_items: list[dict[str, Any]] = []
        try:
            videos = fetch_latest_videos(mid, fallback_name=name)
            seen_bvids = {item["bvid"] for item in seen_data.get(mid, []) if item.get("bvid")}
            for video in videos:
                bvid = video["bvid"]
                if bvid not in seen_bvids:
                    detail = fetch_video_detail_with_ytdlp(
                        bvid=bvid,
                        fallback_url=video["url"],
                        fallback_up_name=name,
                    )
                    detail["first_seen_at"] = current_time_str()
                    new_videos.append(detail)
                    new_seen_items.append(detail)
                    seen_bvids.add(bvid)
        except Exception as exc:
            print(safe_console_text(f"[WARN] failed to fetch {name} ({mid}): {exc}"))
            failed_ups.append({"name": name, "mid": mid, "reason": str(exc)})
        else:
            seen_data[mid] = merge_seen(seen_data.get(mid, []), new_seen_items)

    save_seen_videos(SEEN_PATH, seen_data)
    write_updates(UPDATES_PATH, new_videos, failed_ups)

    print(safe_console_text(f"Done. New videos: {len(new_videos)}"))
    print(safe_console_text(f"Output: {UPDATES_PATH}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
