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

## keys.config format

You can start from `keys.config.example` and fill in your own values locally.

Basic example:

```ini
API_KEYS="your_first_key"
API_KEYS="your_second_key"
OUTPUT_DIR="./output"
PROXY_URL=""
BILIBILI_COOKIES="./bilibili.txt"
```

`PROXY_URL` is only a generic fallback. In more complex server environments, prefer per-service proxy settings.

## Bilibili Stability

Tencent Cloud Hong Kong servers may hit Bilibili `412` checks or mid-download interruptions while fetching audio.

- `412` usually means you need valid Bilibili cookies.
- Export cookies in Netscape format and save them as `bilibili.txt`.
- Then set this in `keys.config`:

```ini
BILIBILI_COOKIES="./bilibili.txt"
```

For Bilibili requests, the script passes explicit request headers and these `yt-dlp` stability options:

```bash
--continue
--retries 10
--fragment-retries 10
--file-access-retries 10
--retry-sleep 2
--http-chunk-size 512K
```

You can override those defaults in `keys.config`:

```ini
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

## Usage

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

Full flow:

```bash
source .venv/bin/activate
./auto_sub.sh "https://www.bilibili.com/video/BV1jB9XB1EeZ/" --summarize
```

Expected behavior:

1. Bilibili title is resolved successfully.
2. yt-dlp downloads audio with retry and resume behavior.
3. Groq Whisper uses `GROQ_PROXY_URL` when configured.
4. DeepSeek summary runs direct or via `DEEPSEEK_PROXY_URL`, depending on config.
5. The output directory contains `.txt`, `.pdf`, and `.summary.md`.
