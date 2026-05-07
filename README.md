# Bili Sub

Cross-platform Bilibili subtitle/transcript helper for Windows and Linux/cloud hosts.

## Required files

- `bili_groq.py`: main workflow, downloads subtitles/audio and calls Groq Whisper when needed.
- `keys.config`: stores API keys and optional output/proxy settings.
- `txt2pdf.py`: optional TXT to PDF conversion.
- `font.ttf`: font used by PDF export.

## Optional launchers

- `auto_sub.ps1`: Windows PowerShell launcher.
- `auto_sub.sh`: Linux/cloud launcher.

## keys.config format

Repeat `API_KEYS` for multiple keys:

```ini
API_KEYS="your_first_key"
API_KEYS="your_second_key"
PROXY_URL="http://127.0.0.1:7890"
OUTPUT_DIR="./output"
BILIBILI_COOKIES="./bilibili.txt"
```

`PROXY_URL` will be used for both `yt-dlp` and Groq API requests.
You can start from `keys.config.example` and fill in your own keys locally.

## Bilibili Stability

Tencent Cloud Hong Kong servers may hit Bilibili `412` checks or mid-download interruptions while fetching audio.

- `412` usually means you need valid Bilibili cookies.
- Export cookies in Netscape format and save them as `bilibili.txt`.
- Then set this in `keys.config`:

```ini
BILIBILI_COOKIES="./bilibili.txt"
```

For Bilibili requests, the script now passes explicit request headers and these stability options to `yt-dlp`:

```bash
--continue
--retries 10
--fragment-retries 10
--file-access-retries 10
--retry-sleep 2
--http-chunk-size 512K
```

You can override those defaults in `keys.config` with:

```ini
YTDLP_RETRIES=10
YTDLP_FRAGMENT_RETRIES=10
YTDLP_FILE_ACCESS_RETRIES=10
YTDLP_RETRY_SLEEP=2
YTDLP_HTTP_CHUNK_SIZE="512K"
```

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

Output files are written to `./output` by default unless `OUTPUT_DIR` or `--output-dir` is set.

If Bilibili audio download times out on Windows, the current network may be unable to reach `*.mcdn.bilivideo.cn:8082`. In that case, set `PROXY_URL` or run the same command on a cloud host with direct access.
