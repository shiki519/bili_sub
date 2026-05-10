import argparse
import glob
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

try:
    from opencc import OpenCC
except ImportError:
    OpenCC = None

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"
CONFIG_FILE_NAME = "keys.config"
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
TEMP_AUDIO = SCRIPT_DIR / "temp_download.m4a"
WORK_DIR = SCRIPT_DIR / "temp_chunks"
TASK_FILE = SCRIPT_DIR / ".current_task_url"
TITLE_FILE = SCRIPT_DIR / ".current_task_title"
TEMP_SUB_PREFIX = "temp_sub"
current_key_index = 0
ASR_PROMPT_LINES = (
    "请将这段中文视频音频转写为简体中文，尽量补齐标点。",
    "保留人名、地名、机构名、日期和数字。",
    "不要加入解释、总结或额外指令。",
    "如果音频中出现广告、口播、玩笑或重复句，也按原文转写。",
)
ASR_PROMPT = "".join(ASR_PROMPT_LINES)
SUMMARY_USER_PREFIX = "以下是视频转写文本，请按照要求分析：\n\n"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download Bilibili audio and transcribe it with Groq Whisper."
    )
    parser.add_argument("url", nargs="?", help="Bilibili video URL")
    parser.add_argument(
        "--keys-file",
        default=str(SCRIPT_DIR / CONFIG_FILE_NAME),
        help="Path to keys.config",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for txt/pdf output (default: ./output or config/env override)",
    )
    parser.add_argument(
        "--proxy-url",
        default=None,
        help="Generic fallback HTTP/HTTPS proxy URL for supported requests",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Generate a PDF after writing the TXT result",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep downloaded audio and chunk cache after success",
    )
    parser.add_argument(
        "--skip-native-sub",
        action="store_true",
        help="Skip downloading Bilibili native subtitles and go straight to ASR",
    )
    parser.add_argument(
        "--summarize",
        action="store_true",
        help="Summarize the generated TXT with DeepSeek after transcription",
    )
    parser.add_argument(
        "--summarize-file",
        default=None,
        help="Summarize an existing TXT file with DeepSeek without downloading/transcribing",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Only download audio or use native subtitles, without Groq or DeepSeek",
    )
    parser.add_argument(
        "--transcribe-file",
        default=None,
        help="Transcribe an existing local audio file without downloading it again",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Title to use with --transcribe-file",
    )
    return parser.parse_args()


def strip_wrapped_quotes(value):
    value = value.strip()
    quote_pairs = {
        "'": "'",
        '"': '"',
        "“": "”",
        "‘": "’",
    }
    if len(value) >= 2 and value[0] in quote_pairs and value[-1] == quote_pairs[value[0]]:
        return value[1:-1]
    return value


def load_runtime_config(config_path):
    api_keys = []
    config = {
        "proxy_url": "",
        "ytdlp_proxy_url": "",
        "groq_proxy_url": "",
        "deepseek_proxy_url": "",
        "output_dir": "",
        "deepseek_api_key": "",
        "deepseek_base_url": "https://api.deepseek.com",
        "deepseek_model": "deepseek-chat",
        "deepseek_prompt_file": "prompts/news_analysis.md",
        "deepseek_retries": "3",
        "deepseek_timeout": "300",
        "bilibili_cookies": "",
        "ytdlp_audio_format": "30216/30232/30280/ba[ext=m4a]/ba/bestaudio",
        "ytdlp_retries": "30",
        "ytdlp_fragment_retries": "30",
        "ytdlp_file_access_retries": "30",
        "ytdlp_retry_sleep": "5",
        "ytdlp_http_chunk_size": "512K",
    }

    env_keys = os.environ.get("BILI_SUB_API_KEYS", "").strip()
    if env_keys:
        api_keys.extend([item.strip() for item in env_keys.split(",") if item.strip()])

    cfg_path = Path(config_path).expanduser()
    if cfg_path.exists():
        for raw_line in cfg_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            match = re.match(r"^([A-Za-z0-9_]+)\s*=\s*(.+)$", line)
            if not match:
                continue

            key_name, raw_value = match.groups()
            value = strip_wrapped_quotes(raw_value)

            if key_name in {"API_KEYS", "API_KEY"} and value:
                api_keys.append(value)
            elif key_name == "PROXY_URL":
                config["proxy_url"] = value
            elif key_name in {"DOWNLOAD_DIR", "OUTPUT_DIR"}:
                config["output_dir"] = value
            elif key_name == "YTDLP_PROXY_URL":
                config["ytdlp_proxy_url"] = value
            elif key_name == "GROQ_PROXY_URL":
                config["groq_proxy_url"] = value
            elif key_name == "DEEPSEEK_PROXY_URL":
                config["deepseek_proxy_url"] = value
            elif key_name == "DEEPSEEK_API_KEY":
                config["deepseek_api_key"] = value
            elif key_name == "DEEPSEEK_BASE_URL" and value:
                config["deepseek_base_url"] = value
            elif key_name == "DEEPSEEK_MODEL" and value:
                config["deepseek_model"] = value
            elif key_name == "DEEPSEEK_PROMPT_FILE" and value:
                config["deepseek_prompt_file"] = value
            elif key_name == "DEEPSEEK_RETRIES" and value:
                config["deepseek_retries"] = value
            elif key_name == "DEEPSEEK_TIMEOUT" and value:
                config["deepseek_timeout"] = value
            elif key_name == "BILIBILI_COOKIES":
                config["bilibili_cookies"] = value
            elif key_name == "YTDLP_AUDIO_FORMAT" and value:
                config["ytdlp_audio_format"] = value
            elif key_name == "YTDLP_RETRIES" and value:
                config["ytdlp_retries"] = value
            elif key_name == "YTDLP_FRAGMENT_RETRIES" and value:
                config["ytdlp_fragment_retries"] = value
            elif key_name == "YTDLP_FILE_ACCESS_RETRIES" and value:
                config["ytdlp_file_access_retries"] = value
            elif key_name == "YTDLP_RETRY_SLEEP" and value:
                config["ytdlp_retry_sleep"] = value
            elif key_name == "YTDLP_HTTP_CHUNK_SIZE" and value:
                config["ytdlp_http_chunk_size"] = value

    env_overrides = {
        "BILI_SUB_PROXY_URL": "proxy_url",
        "PROXY_URL": "proxy_url",
        "BILI_SUB_OUTPUT_DIR": "output_dir",
        "OUTPUT_DIR": "output_dir",
        "YTDLP_PROXY_URL": "ytdlp_proxy_url",
        "GROQ_PROXY_URL": "groq_proxy_url",
        "DEEPSEEK_PROXY_URL": "deepseek_proxy_url",
        "DEEPSEEK_API_KEY": "deepseek_api_key",
        "DEEPSEEK_BASE_URL": "deepseek_base_url",
        "DEEPSEEK_MODEL": "deepseek_model",
        "DEEPSEEK_PROMPT_FILE": "deepseek_prompt_file",
        "DEEPSEEK_RETRIES": "deepseek_retries",
        "DEEPSEEK_TIMEOUT": "deepseek_timeout",
        "BILIBILI_COOKIES": "bilibili_cookies",
        "YTDLP_AUDIO_FORMAT": "ytdlp_audio_format",
        "YTDLP_RETRIES": "ytdlp_retries",
        "YTDLP_FRAGMENT_RETRIES": "ytdlp_fragment_retries",
        "YTDLP_FILE_ACCESS_RETRIES": "ytdlp_file_access_retries",
        "YTDLP_RETRY_SLEEP": "ytdlp_retry_sleep",
        "YTDLP_HTTP_CHUNK_SIZE": "ytdlp_http_chunk_size",
    }
    for env_name, config_key in env_overrides.items():
        if env_name in os.environ:
            config[config_key] = os.environ[env_name].strip()

    unique_keys = []
    seen = set()
    for item in api_keys:
        if item not in seen:
            unique_keys.append(item)
            seen.add(item)

    return {
        "api_keys": unique_keys,
        **config,
    }


def get_output_dir(cli_output_dir, config_output_dir):
    raw_value = cli_output_dir or config_output_dir
    if raw_value:
        return Path(raw_value).expanduser().resolve()
    return DEFAULT_OUTPUT_DIR


def resolve_ytdlp_command():
    binary = shutil.which("yt-dlp")
    if binary:
        return [binary]
    if importlib.util.find_spec("yt_dlp"):
        return [sys.executable, "-m", "yt_dlp"]
    raise RuntimeError(
        "yt-dlp is not installed. Install it with `python -m pip install yt-dlp`."
    )


def resolve_optional_path(raw_path):
    if not raw_path:
        return None
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = SCRIPT_DIR / path
    return path.resolve()


def build_ytdlp_command(runtime_config, needs_cookies=False):
    ytdlp_proxy_url = runtime_config["ytdlp_proxy_url"] or runtime_config["proxy_url"]
    print(f"[ytdlp] proxy: {ytdlp_proxy_url or 'direct'}")
    cmd = resolve_ytdlp_command() + [
        "--socket-timeout",
        "60",
        "--continue",
        "--retries",
        str(runtime_config["ytdlp_retries"]),
        "--fragment-retries",
        str(runtime_config["ytdlp_fragment_retries"]),
        "--file-access-retries",
        str(runtime_config["ytdlp_file_access_retries"]),
        "--retry-sleep",
        str(runtime_config["ytdlp_retry_sleep"]),
        "--http-chunk-size",
        str(runtime_config["ytdlp_http_chunk_size"]),
        "--add-header",
        "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        "--add-header",
        "Referer: https://www.bilibili.com/",
    ]
    try:
        ffmpeg_path = resolve_ffmpeg_command()
        cmd += ["--ffmpeg-location", ffmpeg_path]
    except RuntimeError:
        pass

    cookies_path = resolve_optional_path(runtime_config["bilibili_cookies"])
    if cookies_path and cookies_path.is_file() and os.access(cookies_path, os.R_OK):
        print(f"[info] using Bilibili cookies file: {cookies_path}")
        cmd += ["--cookies", str(cookies_path)]
    elif needs_cookies or runtime_config["bilibili_cookies"]:
        print("[warn] BILIBILI_COOKIES not found or unreadable, continue without cookies")

    if ytdlp_proxy_url:
        cmd += ["--proxy", ytdlp_proxy_url]
    return cmd


def ensure_command_available(command_name):
    if shutil.which(command_name):
        return
    raise RuntimeError(
        f"`{command_name}` was not found in PATH. Please install it before running."
    )


def resolve_ffmpeg_command():
    binary = shutil.which("ffmpeg")
    if binary:
        return binary
    if imageio_ffmpeg is not None:
        return imageio_ffmpeg.get_ffmpeg_exe()
    raise RuntimeError(
        "ffmpeg was not found. Install system ffmpeg or `python -m pip install imageio-ffmpeg`."
    )


def run_command(command, capture_output=False, quiet=False):
    kwargs = {
        "check": True,
        "text": True,
    }
    if capture_output:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    elif quiet:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL

    result = subprocess.run(command, **kwargs)
    if capture_output:
        return result.stdout.strip()
    return ""


def wipe_cache(reason, keep_task_file=False):
    print(f"[cleanup] {reason}")
    if TEMP_AUDIO.exists():
        TEMP_AUDIO.unlink()
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    for file_path in SCRIPT_DIR.glob(f"{TEMP_SUB_PREFIX}*.srt"):
        file_path.unlink()
    if TITLE_FILE.exists():
        TITLE_FILE.unlink()
    if not keep_task_file and TASK_FILE.exists():
        TASK_FILE.unlink()


def check_task_consistency(new_url):
    if not new_url:
        return

    last_url = ""
    if TASK_FILE.exists():
        last_url = TASK_FILE.read_text(encoding="utf-8").strip()

    if last_url and last_url != new_url:
        wipe_cache("detected a new URL, clearing old cache", keep_task_file=True)

    TASK_FILE.write_text(new_url, encoding="utf-8")


def get_current_key(api_keys):
    return api_keys[current_key_index % len(api_keys)]


def rotate_key(api_keys):
    global current_key_index
    current_key_index += 1
    next_index = current_key_index % len(api_keys) + 1
    print(f"[api] switched to key #{next_index}")


def get_video_title(url, runtime_config):
    cmd = build_ytdlp_command(runtime_config, needs_cookies=True) + [
        "--get-filename",
        "-o",
        "%(title)s",
        url,
    ]
    return run_command(cmd, capture_output=True) or "Unknown_Video"


def save_current_title(title):
    if title and title != "Unknown_Video":
        TITLE_FILE.write_text(title, encoding="utf-8")


def load_saved_title():
    if not TITLE_FILE.exists():
        return ""
    title = TITLE_FILE.read_text(encoding="utf-8").strip()
    return title


def load_cached_title(runtime_config, url=""):
    if url:
        try:
            title = get_video_title(url, runtime_config)
            save_current_title(title)
            return title
        except Exception:
            pass

    saved_title = load_saved_title()
    if saved_title:
        return saved_title

    return "Cached_Video"


def download_native_sub(url, runtime_config):
    print("[step 1] checking Bilibili native subtitles")
    for file_path in SCRIPT_DIR.glob(f"{TEMP_SUB_PREFIX}*.srt"):
        file_path.unlink()

    cmd = build_ytdlp_command(runtime_config, needs_cookies=True) + [
        "--write-subs",
        "--skip-download",
        "--sub-langs",
        "zh-CN,zh-Hans,ai-zh,en",
        "--sub-format",
        "srt",
        "-o",
        TEMP_SUB_PREFIX,
        url,
    ]
    try:
        run_command(cmd, quiet=True)
    except subprocess.CalledProcessError:
        return None

    files = sorted(SCRIPT_DIR.glob(f"{TEMP_SUB_PREFIX}*.srt"))
    return files[0] if files else None


def download_audio(url, runtime_config):
    print("[step 2] downloading audio")
    if TEMP_AUDIO.exists() and TEMP_AUDIO.stat().st_size > 1024:
        print("[cache] reusing downloaded audio")
        return TEMP_AUDIO, load_cached_title(runtime_config, url)

    title = get_video_title(url, runtime_config)
    save_current_title(title)
    print(f"[video] title: {title}")
    print(f"[ytdlp] audio format: {runtime_config['ytdlp_audio_format']}")

    cmd = build_ytdlp_command(runtime_config, needs_cookies=True) + [
        "-x",
        "-f",
        runtime_config["ytdlp_audio_format"],
        "--audio-format",
        "m4a",
        "-o",
        str(TEMP_AUDIO),
        url,
    ]
    run_command(cmd)
    if not TEMP_AUDIO.exists():
        raise RuntimeError("audio download failed")
    return TEMP_AUDIO, title


def compress_and_split(input_file):
    print("[step 3] preprocessing audio")
    WORK_DIR.mkdir(exist_ok=True)

    existing_chunks = sorted(WORK_DIR.glob("chunk_*.opus"))
    if existing_chunks:
        print(f"[cache] reusing {len(existing_chunks)} chunk(s)")
        return existing_chunks

    print("[audio] splitting into 10-minute chunks")
    pattern = WORK_DIR / "chunk_%03d.opus"
    ffmpeg_cmd = resolve_ffmpeg_command()
    run_command(
        [
            ffmpeg_cmd,
            "-i",
            str(input_file),
            "-f",
            "segment",
            "-segment_time",
            "600",
            "-reset_timestamps",
            "1",
            "-ac",
            "1",
            "-b:a",
            "32k",
            "-c:a",
            "libopus",
            str(pattern),
            "-y",
            "-loglevel",
            "error",
        ]
    )
    return sorted(WORK_DIR.glob("chunk_*.opus"))


def call_groq_api(filepath, chunk_index, total_chunks, api_keys, runtime_config):
    cache_file = filepath.with_suffix(filepath.suffix + ".txt")
    if cache_file.exists() and cache_file.stat().st_size > 0:
        print(f"[cache] chunk {chunk_index}/{total_chunks} already transcribed")
        return cache_file.read_text(encoding="utf-8")

    if not api_keys:
        raise RuntimeError(
            "No API key found. Add one or more keys to keys.config with API_KEYS=\"...\"."
        )

    groq_proxy_url = runtime_config["groq_proxy_url"] or runtime_config["proxy_url"]
    proxies = {"http": groq_proxy_url, "https": groq_proxy_url} if groq_proxy_url else None
    max_retries = max(5, len(api_keys) * 2)
    for attempt in range(max_retries):
        current_key = get_current_key(api_keys)
        headers = {"Authorization": f"Bearer {current_key}"}

        try:
            print(f"[api] Groq proxy: {groq_proxy_url or 'direct'}")
            with filepath.open("rb") as audio_file:
                files = {
                    "file": (filepath.name, audio_file),
                    "model": (None, "whisper-large-v3-turbo"),
                    "language": (None, "zh"),
                    "prompt": (None, ASR_PROMPT),
                    "response_format": (None, "text"),
                }
                print(f"[api] uploading chunk {chunk_index}/{total_chunks}")
                response = requests.post(
                    GROQ_URL,
                    headers=headers,
                    files=files,
                    proxies=proxies,
                    timeout=120,
                )

            if response.status_code in {401, 403, 429}:
                body_preview = (response.text or "")[:300].replace("\n", " ")
                print(f"[api] HTTP {response.status_code}: {body_preview}")
                if response.status_code == 429:
                    print("[api] quota hit, rotating key")
                else:
                    print(f"[api] key rejected with HTTP {response.status_code}, rotating key")
                rotate_key(api_keys)
                time.sleep(2)
                continue

            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}: {response.text[:120]}")

            text = response.text
            cache_file.write_text(text, encoding="utf-8")
            return text

        except Exception as exc:
            print(f"[api] chunk {chunk_index}/{total_chunks} failed ({attempt + 1}/{max_retries}): {exc}")
            time.sleep(3)

    raise RuntimeError("All configured API keys failed for this chunk.")


def normalize_srt_text(text):
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.isdigit():
            continue
        if "-->" in line:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def simplify_text(text):
    if OpenCC is None:
        return text
    try:
        return OpenCC("t2s").convert(text)
    except Exception:
        return text


def sanitize_title(title):
    safe_title = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff _-]+", "", title).strip()
    return safe_title or "result_recovered"


def resolve_local_path(path_value):
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = SCRIPT_DIR / path
    return path.resolve()


def emit_result(name, path_value):
    print(f"RESULT_{name}={Path(path_value).resolve()}")


def convert_and_save(text, title, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_title = sanitize_title(title)
    output_path = output_dir / f"{safe_title}.txt"
    final_text = simplify_text(text)
    output_path.write_text(final_text, encoding="utf-8")
    print(f"[save] txt written to {output_path}")
    return output_path


def maybe_generate_pdf(txt_path):
    try:
        from txt2pdf import convert_txt_to_pdf
    except ImportError as exc:
        print(f"[pdf] skipped: {exc}")
        return None

    return convert_txt_to_pdf(str(txt_path))


def transcribe_audio_file(audio_path, title, runtime_config, output_dir):
    audio_file = resolve_local_path(audio_path)
    if not audio_file.exists():
        raise RuntimeError(f"Audio file not found: {audio_file}")

    print(f"[step 3] using audio file: {audio_file}")
    chunks = compress_and_split(audio_file)
    if not chunks:
        raise RuntimeError("No audio chunks were generated.")

    print(f"[step 4] transcribing {len(chunks)} chunk(s)")
    final_parts = []
    for index, chunk in enumerate(chunks, start=1):
        part_text = call_groq_api(
            chunk,
            index,
            len(chunks),
            runtime_config["api_keys"],
            runtime_config,
        )
        final_parts.append(part_text)

    return convert_and_save("\n".join(final_parts), title, output_dir)


def load_prompt_file(prompt_path):
    prompt_file = Path(prompt_path).expanduser()
    if not prompt_file.is_absolute():
        prompt_file = SCRIPT_DIR / prompt_file
    prompt_file = prompt_file.resolve()

    if not prompt_file.exists():
        raise RuntimeError(f"Prompt file not found: {prompt_file}")

    prompt_text = prompt_file.read_text(encoding="utf-8").strip()
    if not prompt_text:
        raise RuntimeError(f"Prompt file is empty: {prompt_file}")
    return prompt_text


def preclean_transcript(text):
    cleaned = text.replace("\ufeff", "").replace("\x00", "")
    prompt_residue = set(ASR_PROMPT_LINES)
    prompt_residue.add(ASR_PROMPT)

    kept_lines = []
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            kept_lines.append("")
            continue
        if line in prompt_residue:
            continue
        kept_lines.append(raw_line.rstrip())

    return "\n".join(kept_lines).strip()


def call_deepseek_summary(transcript_text, prompt_text, runtime_config):
    api_key = runtime_config["deepseek_api_key"]
    if not api_key:
        raise RuntimeError("No DeepSeek API key found. Set DEEPSEEK_API_KEY in keys.config or environment.")

    base_url = runtime_config["deepseek_base_url"].rstrip("/")
    request_url = f"{base_url}/chat/completions"
    deepseek_proxy_url = runtime_config["deepseek_proxy_url"]
    proxies = {"http": deepseek_proxy_url, "https": deepseek_proxy_url} if deepseek_proxy_url else None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": runtime_config["deepseek_model"],
        "messages": [
            {
                "role": "system",
                "content": prompt_text,
            },
            {
                "role": "user",
                "content": SUMMARY_USER_PREFIX + transcript_text,
            },
        ],
        "temperature": 0.2,
        "max_tokens": 8192,
        "stream": False,
    }
    max_retries = max(1, int(runtime_config["deepseek_retries"]))
    timeout_seconds = max(30, int(runtime_config["deepseek_timeout"]))
    last_error = ""

    for attempt in range(max_retries):
        attempt_number = attempt + 1
        print(f"[summary] DeepSeek attempt {attempt_number}/{max_retries}")
        print(
            f"[summary] sending transcript to DeepSeek model={runtime_config['deepseek_model']} "
            f"proxy={deepseek_proxy_url or 'direct'}"
        )
        try:
            response = requests.post(
                request_url,
                headers=headers,
                json=payload,
                proxies=proxies,
                timeout=timeout_seconds,
            )

            if response.status_code in {502, 503, 504}:
                raise RuntimeError(f"DeepSeek HTTP {response.status_code}: {(response.text or '')[:200]}")

            if response.status_code != 200:
                raise RuntimeError(f"DeepSeek HTTP {response.status_code}: {(response.text or '')[:200]}")

            try:
                summary_text = response.json()["choices"][0]["message"]["content"].strip()
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise RuntimeError(f"Invalid DeepSeek response: {(response.text or '')[:200]}") from exc

            if not summary_text:
                raise RuntimeError("DeepSeek returned an empty summary.")
            return summary_text

        except (
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.ConnectionError,
            requests.exceptions.ReadTimeout,
            requests.exceptions.Timeout,
        ) as exc:
            last_error = str(exc)
        except RuntimeError as exc:
            last_error = str(exc)
            if "Response ended prematurely" not in last_error and not any(
                code in last_error for code in ("HTTP 502", "HTTP 503", "HTTP 504")
            ):
                raise

        print(f"[summary] attempt {attempt_number} failed: {last_error}")
        if attempt_number < max_retries:
            sleep_seconds = min(5 * (2 ** attempt), 30)
            print(f"[summary] retrying in {sleep_seconds}s")
            time.sleep(sleep_seconds)

    raise RuntimeError(f"DeepSeek summary failed after {max_retries} attempts: {last_error}")


def save_summary(txt_path, summary_text):
    txt_file = Path(txt_path).expanduser().resolve()
    summary_path = txt_file.with_suffix(".summary.md")
    summary_path.write_text(summary_text, encoding="utf-8")
    print(f"[save] summary written to {summary_path}")
    return summary_path


def summarize_txt_file(txt_path, runtime_config):
    txt_file = Path(txt_path).expanduser().resolve()
    if not txt_file.exists():
        raise RuntimeError(f"TXT file not found: {txt_file}")

    print(f"[summary] reading transcript from {txt_file}")
    transcript_text = txt_file.read_text(encoding="utf-8")
    prompt_text = load_prompt_file(runtime_config["deepseek_prompt_file"])
    cleaned_text = preclean_transcript(transcript_text)
    summary_text = call_deepseek_summary(cleaned_text, prompt_text, runtime_config)
    return save_summary(txt_file, summary_text)


def validate_dependencies(will_use_native_sub, will_transcribe):
    if will_use_native_sub or will_transcribe:
        resolve_ytdlp_command()
    if will_transcribe:
        resolve_ffmpeg_command()


def validate_dependencies_for_mode(
    will_use_native_sub=False,
    will_download_audio=False,
    will_transcribe=False,
):
    if will_use_native_sub or will_download_audio or will_transcribe:
        resolve_ytdlp_command()
    if will_transcribe:
        resolve_ffmpeg_command()


def emit_artifacts(txt_path=None, pdf_path=None, summary_path=None, audio_path=None):
    if audio_path:
        emit_result("AUDIO", audio_path)
    if txt_path:
        emit_result("TXT", txt_path)
    if pdf_path:
        emit_result("PDF", pdf_path)
    if summary_path:
        emit_result("SUMMARY", summary_path)


def main():
    args = parse_args()
    runtime_config = load_runtime_config(args.keys_file)
    output_dir = get_output_dir(args.output_dir, runtime_config["output_dir"])
    if args.proxy_url is not None:
        runtime_config["proxy_url"] = args.proxy_url

    if args.summarize_file:
        try:
            summary_path = summarize_txt_file(args.summarize_file, runtime_config)
            emit_artifacts(summary_path=summary_path)
            return 0
        except Exception as exc:
            print(f"[error] {exc}")
            return 1

    if args.transcribe_file:
        try:
            validate_dependencies_for_mode(will_transcribe=True)
            title = args.title or load_saved_title() or Path(args.transcribe_file).stem
            generated_txt = transcribe_audio_file(
                args.transcribe_file,
                title,
                runtime_config,
                output_dir,
            )
            pdf_path = maybe_generate_pdf(generated_txt) if args.pdf else None
            emit_artifacts(txt_path=generated_txt, pdf_path=pdf_path)
            if args.summarize:
                print("[info] --summarize is ignored with --transcribe-file. Run --summarize-file separately.")
            return 0
        except Exception as exc:
            print(f"[error] {exc}")
            return 1

    if not args.url and not TEMP_AUDIO.exists():
        print(
            "Usage: python bili_groq.py <URL> [--pdf] [--summarize] "
            "| --transcribe-file <audio_path> [--title <title>] "
            "| --summarize-file <txt_path>"
        )
        return 1

    url = args.url or ""
    title = "Video_Result"
    generated_txt = None

    if url:
        check_task_consistency(url)

    try:
        validate_dependencies_for_mode(
            will_use_native_sub=bool(url and not args.skip_native_sub),
            will_download_audio=bool(url),
            will_transcribe=bool(not args.download_only and (url or TEMP_AUDIO.exists())),
        )

        if url and not args.skip_native_sub:
            native_sub = download_native_sub(url, runtime_config)
            if native_sub:
                title = get_video_title(url, runtime_config)
                save_current_title(title)
                raw_text = native_sub.read_text(encoding="utf-8")
                subtitle_text = normalize_srt_text(raw_text)
                generated_txt = convert_and_save(subtitle_text or raw_text, title, output_dir)
                pdf_path = maybe_generate_pdf(generated_txt) if args.pdf else None
                summary_path = None
                if args.summarize and not args.download_only:
                    summary_path = summarize_txt_file(generated_txt, runtime_config)
                emit_artifacts(
                    txt_path=generated_txt,
                    pdf_path=pdf_path,
                    summary_path=summary_path,
                )
                if not args.keep_temp:
                    wipe_cache("native subtitle path finished")
                return 0

        if args.download_only:
            if not url:
                raise RuntimeError("--download-only requires a Bilibili URL.")
            audio_path, title = download_audio(url, runtime_config)
            print(f"[download-only] audio ready for title: {title}")
            emit_artifacts(audio_path=audio_path)
            return 0

        if url:
            _, title = download_audio(url, runtime_config)
        elif TEMP_AUDIO.exists():
            print("[step 2] using existing cached audio")
            title = load_saved_title() or load_cached_title(runtime_config)
        else:
            raise RuntimeError("No URL provided and no cached audio found.")

        generated_txt = transcribe_audio_file(TEMP_AUDIO, title, runtime_config, output_dir)
        pdf_path = maybe_generate_pdf(generated_txt) if args.pdf else None
        summary_path = summarize_txt_file(generated_txt, runtime_config) if args.summarize else None
        emit_artifacts(
            txt_path=generated_txt,
            pdf_path=pdf_path,
            summary_path=summary_path,
        )

        if not args.keep_temp:
            wipe_cache("task finished")
        return 0

    except Exception as exc:
        print(f"[error] {exc}")
        print("[resume] temp files were kept so you can retry the same URL later.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
