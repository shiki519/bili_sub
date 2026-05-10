# Bili Sub

Cross-platform Bilibili subtitle/transcript helper for Windows and Linux/cloud hosts.

## Required files

- `bili_groq.py`: main workflow, downloads subtitles/audio, calls Groq Whisper, and can run DeepSeek summary.
- `keys.config`: stores API keys and runtime options.
- `txt2pdf.py`: optional TXT to PDF conversion.
- `font.ttf`: font used by PDF export.

## Optional launchers

- `auto_sub.ps1`: Windows PowerShell launcher.
- `auto_sub.sh`: Linux/cloud launcher.
- `run_bili_sub.sh`: staged Linux/cloud wrapper for more stable retries and recovery.

## keys.config format

Start from `keys.config.example` and fill in your own local values.

Basic example:

```ini
API_KEYS="your_first_key"
API_KEYS="your_second_key"
OUTPUT_DIR="./output"
PROXY_URL=""
BILIBILI_COOKIES="./bilibili.txt"
```

`PROXY_URL` is only a generic fallback. On servers, prefer the split proxy settings below.

## Bilibili Stability

Tencent Cloud Hong Kong servers may hit Bilibili `412` checks or mid-download interruptions while fetching audio.

- `412` usually means valid Bilibili cookies are required.
- Export cookies in Netscape format and save them as `bilibili.txt`.
- Then set this in `keys.config`:

```ini
BILIBILI_COOKIES="./bilibili.txt"
```

When testing on a local desktop where the browser is already logged in, you can let the script reuse that browser session:

```ini
BILIBILI_COOKIES_FROM_BROWSER="chrome"
```

Supported values follow `yt-dlp` browser names, such as `chrome`, `edge`, `firefox`, or `chrome:Default`. If this is set, Bilibili API subtitle requests and `yt-dlp` calls use the browser cookies first.

You can verify whether the configured cookies are really logged in before testing subtitle APIs:

```powershell
python .\bili_groq.py --check-bilibili-login
```

For automation, require a valid logged-in cookie jar and return non-zero otherwise:

```powershell
python .\bili_groq.py --check-bilibili-login --require-login
```

Expected machine-readable output:

```text
NAV_CODE=0
IS_LOGIN=True
MESSAGE=0
UNAME=your_bilibili_name
```

If `IS_LOGIN=False`, the script can still fall back to `yt-dlp` subtitles or audio download, but Bilibili API or AI subtitles may be unavailable.

The script passes explicit Bilibili headers and these `yt-dlp` stability options:

```bash
--continue
--retries 30
--fragment-retries 30
--file-access-retries 30
--retry-sleep 5
--http-chunk-size 512K
```

It also prefers lower bitrate audio first to reduce download size and CDN interruption risk:

```ini
YTDLP_AUDIO_FORMAT="30216/30232/30280/ba[ext=m4a]/ba/bestaudio"
```

You can override the defaults in `keys.config`:

```ini
YTDLP_AUDIO_FORMAT="30216/30232/30280/ba[ext=m4a]/ba/bestaudio"
YTDLP_RETRIES=30
YTDLP_FRAGMENT_RETRIES=30
YTDLP_FILE_ACCESS_RETRIES=30
YTDLP_RETRY_SLEEP=5
YTDLP_HTTP_CHUNK_SIZE="512K"
```

## Recommended Server Proxy Setup

For Tencent Cloud Hong Kong servers, this split proxy setup is recommended:

```ini
PROXY_URL=""
YTDLP_PROXY_URL=""
GROQ_PROXY_URL="http://127.0.0.1:7890"
DEEPSEEK_PROXY_URL=""
```

Why:

1. `GROQ_PROXY_URL` can help when direct access to Groq returns `403`.
2. `DEEPSEEK_PROXY_URL` is empty by default, which means DeepSeek connects directly.
3. `PROXY_URL` is only a generic fallback, and it is usually better not to force every service through the same proxy on unstable server networks.
4. `DEEPSEEK_RETRIES` and `DEEPSEEK_TIMEOUT` help with occasional summary-stage connection interruptions.

## Python dependencies

```powershell
python -m pip install -r requirements.txt
```

## System dependencies

- `yt-dlp` if you do not install it from `requirements.txt`
- `ffmpeg` is optional if you install `imageio-ffmpeg` from `requirements.txt`

## Standard usage

Windows:

```powershell
.\auto_sub.ps1 "https://www.bilibili.com/video/BV..."
.\auto_sub.ps1 "https://www.bilibili.com/video/BV..." -Summarize
```

Linux/cloud:

```bash
chmod +x auto_sub.sh
./auto_sub.sh "https://www.bilibili.com/video/BV..."
./auto_sub.sh "https://www.bilibili.com/video/BV..." --summarize
```

Direct Python:

```powershell
python .\bili_groq.py "https://www.bilibili.com/video/BV..." --pdf
python .\bili_groq.py "https://www.bilibili.com/video/BV..." --pdf --summarize
python .\bili_groq.py --summarize-file "output\英国衰弱的不像话了.txt"
```

## Staged commands

Download only:

```bash
python bili_groq.py "https://www.bilibili.com/video/BVxxxx/" --download-only
```

Behavior:

1. Checks Bilibili API / AI subtitles first.
2. Falls back to `yt-dlp` visible `.srt` subtitles.
3. Only if both subtitle paths fail, downloads audio to `temp_download.m4a`.
4. Does not call Groq.
5. Does not call DeepSeek.

Subtitle priority:

- Bilibili API / AI subtitles
- `yt-dlp` visible `.srt` subtitles
- Audio download + Groq

Notes:

- `danmaku.xml` is bullet chat, not spoken subtitle text, so it is not used as the default transcript source.
- When subtitle paths succeed, the script writes both `output/<title>.txt` and `output/<title>.srt` for debugging.
- When Bilibili API subtitles are available, `--download-only` returns `RESULT_TXT`, `RESULT_SRT`, and optional `RESULT_PDF` directly without downloading audio.

Machine-readable output:

```text
RESULT_TITLE=视频真实标题
RESULT_AUDIO=/abs/path/to/temp_download.m4a
```

or:

```text
RESULT_TXT=/abs/path/to/output/xxx.txt
RESULT_SRT=/abs/path/to/output/xxx.srt
RESULT_PDF=/abs/path/to/output/xxx.pdf
```

Transcribe an existing audio file:

```bash
python bili_groq.py --transcribe-file temp_download.m4a --title "视频标题" --pdf
```

Behavior:

1. Splits the existing audio into chunks.
2. Calls Groq Whisper.
3. Writes `output/<title>.txt`.
4. Does not redownload the video.
5. Does not call DeepSeek.

Machine-readable output:

```text
RESULT_TXT=/abs/path/to/output/xxx.txt
RESULT_PDF=/abs/path/to/output/xxx.pdf
```

Summarize an existing transcript:

```bash
python bili_groq.py --summarize-file "output/英国衰弱的不像话了.txt"
```

Machine-readable output:

```text
RESULT_SUMMARY=/abs/path/to/output/xxx.summary.md
```

## Wrapper flow

For server or OpenClaw usage, prefer the staged wrapper:

```bash
chmod +x run_bili_sub.sh
./run_bili_sub.sh "https://www.bilibili.com/video/BVxxxx/"
```

What it does:

1. Changes to the project root.
2. Optionally runs `git pull --ff-only` when `BILI_SUB_GIT_PULL=1`.
3. Activates `.venv` when present.
4. Checks `mihomo.service` with `systemctl --user` and probes port `127.0.0.1:7890`.
5. Runs `download-only`, `transcribe-file`, and `summarize-file` as separate stages.
6. Retries each stage independently.
7. Keeps successful earlier-stage artifacts so later retries do not restart the whole pipeline.

Successful wrapper output:

```text
RESULT_TXT=/home/ubuntu/projects/bili_sub/output/xxx.txt
RESULT_PDF=/home/ubuntu/projects/bili_sub/output/xxx.pdf
RESULT_SUMMARY=/home/ubuntu/projects/bili_sub/output/xxx.summary.md
```

Failure output:

```text
[wrapper] failed at stage: download/transcribe/summary
[wrapper] log: logs/run_xxx.log
```

## Verification

DeepSeek summary only:

```bash
source .venv/bin/activate
python bili_groq.py --summarize-file "output/英国衰弱的不像话了.txt"
```

Expected log:

```text
[summary] sending transcript to DeepSeek model=deepseek-chat proxy=direct
```

Full staged flow:

```bash
source .venv/bin/activate
./run_bili_sub.sh "https://www.bilibili.com/video/BV1jB9XB1EeZ/"
```

Expected behavior:

1. Bilibili title is resolved successfully.
2. yt-dlp downloads audio with retry and resume behavior.
3. Groq Whisper uses `GROQ_PROXY_URL` when configured.
4. DeepSeek summary runs direct or via `DEEPSEEK_PROXY_URL`, depending on config.
5. The output directory contains `.txt`, `.pdf`, and `.summary.md`.
