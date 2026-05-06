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
```

`PROXY_URL` will be used for both `yt-dlp` and Groq API requests.
You can start from `keys.config.example` and fill in your own keys locally.

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
chmod +x auto_sub.sh auto_sub_simple.sh
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
