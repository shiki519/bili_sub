---
name: bili-sub-video-summary
description: Process Bilibili video links in Feishu — subtitle extraction, audio transcription, summarization, and Feishu doc creation. Trigger when users ask to "拉字幕", "转文字", "总结", "生成文档", or send a B站 video link with intent to process. Do NOT trigger for code discussion, environment debugging, or log checking.
---

# bili-sub-video-summary

Automate B站 video subtitle/transcription/summary workflow via `bili_sub` on the server.

---

## Trigger Examples

- "总结这个 B 站视频：https://www.bilibili.com/video/BV..."
- "拉一下这个视频的字幕：https://b23.tv/..."
- "帮我转写并总结这个视频：\<B站链接\>"
- "跑一下 bili_sub：\<B站链接\>"
- User sends a B站 link in Feishu group with intent to process subtitles/summary.

---

## Server Paths

| Item | Path |
|---|---|
| Project root | `/home/ubuntu/projects/bili_sub` |
| Main script | `/home/ubuntu/projects/bili_sub/run_bili_sub.sh` |
| Config | `/home/ubuntu/projects/bili_sub/keys.config` |
| B站 cookies | `/home/ubuntu/projects/bili_sub/bilibili.txt` |
| Output dir | `/home/ubuntu/projects/bili_sub/output` |
| Log dir | `/home/ubuntu/projects/bili_sub/logs` |

---

## Safety Rules

Do NOT output in replies:

- Groq API key
- DeepSeek API key
- B站 cookies / SESSDATA / bili_jct
- Proxy subscription URLs
- mihomo full config
- `keys.config` content

Safe to output:

- Video title
- Generated file paths
- Feishu doc link
- Brief error reason
- Log file path

---

## Preflight Checks

Only run when the user explicitly asks to check the environment, or after consecutive failures.

### 1. Check B站 login status

```bash
cd /home/ubuntu/projects/bili_sub
source .venv/bin/activate
python bili_groq.py --check-bilibili-login --require-login
```

Expected: `IS_LOGIN=True`

Failure reply: "B 站 cookies 当前不是登录态，需要重新从已登录且能看到字幕的浏览器导出 bilibili.txt，并上传到服务器。"

### 2. Check mihomo / Groq proxy

```bash
systemctl --user status mihomo.service --no-pager -l
ss -lntp | grep -E '7890|7891|9090'
```

Expected: `mihomo.service active`, `127.0.0.1:7890 listening`

---

## Main Command

```bash
cd /home/ubuntu/projects/bili_sub
./run_bili_sub.sh "<B站视频链接>"
```

Example:

```bash
cd /home/ubuntu/projects/bili_sub
./run_bili_sub.sh "https://www.bilibili.com/video/BV1jB9XB1EeZ/"
```

### Expected Flow

```plaintext
B站 API / AI 字幕
→ yt-dlp visible .srt subtitles
→ low-bitrate audio download (30216)
→ Groq Whisper transcription
→ DeepSeek summarization
```

If subtitles succeed, output includes:

```plaintext
RESULT_TXT=...
RESULT_SRT=...
RESULT_PDF=...
RESULT_SUMMARY=...
```

If no subtitles, audio download first:

```plaintext
RESULT_AUDIO=...
```

Then transcription + summarization continue automatically.

---

## Parse Output

Extract from script output:

```plaintext
RESULT_TITLE=
RESULT_AUTHOR=
RESULT_BVID=
RESULT_AID=
RESULT_CID=
RESULT_PAGE=
RESULT_ORIGINAL_URL=
RESULT_CANONICAL_URL=
RESULT_TXT=
RESULT_SRT=
RESULT_PDF=
RESULT_SUMMARY=
```

Key file: `RESULT_SUMMARY=` → typically `/home/ubuntu/projects/bili_sub/output/<title>.summary.md`

For Feishu document metadata under the title:

- `UP主：` MUST use `RESULT_AUTHOR`
- `视频链接：` MUST use `RESULT_CANONICAL_URL`
- Do NOT parse these fields from DeepSeek summary content.
- Do NOT guess these fields from the model or from the document title.

---

## Create Feishu Doc

After successful processing:

1. Read `RESULT_SUMMARY` file content
2. Create a Feishu doc as a sub-page under the wiki node `EZ5FwoP2aiBVbnkyVSOcMyPSnYf` in wiki space `ZgEcw6JqoiY1wekIMi1ccAv7n4g` ("B站视频总结" 知识库)
3. Title format: `<视频标题> - 总结`
4. Under the title, write video metadata from machine-readable output: `UP主：<RESULT_AUTHOR>` and `视频链接：<RESULT_CANONICAL_URL>`.
5. **Write the entire summary.md content as-is** into the document body after the metadata. Do not restructure, truncate, or reformat.
6. Never use DeepSeek summary text as the source for `UP主：` or `视频链接：`; use only `RESULT_AUTHOR` and `RESULT_CANONICAL_URL`.
7. Use `wiki_node` parameter when creating the doc (do NOT pass `wiki_space` — the two are mutually exclusive)
8. [默认必做] Attach the PDF file (`RESULT_PDF`) to the doc using `feishu_doc_media`. Copy to `/tmp/` first if needed. **约束**：
   - **必须默认附上 PDF**，不要省略或询问用户
   - **只附 PDF**，不要附 txt、srt、summary.md 等其他文件
   - **保持原始中文文件名**，复制到 `/tmp/` 时不要改成英文名
9. Reply with the Feishu doc link.

---

## Success Reply Template

完成后回复用户：

```text
已完成这个 B 站视频的字幕/转写和总结。

飞书文档：<文档链接>

本次生成文件：
- TXT: <RESULT_TXT>
- SRT: <RESULT_SRT，如有>
- PDF: <RESULT_PDF，如有>
- Summary: <RESULT_SUMMARY>
```

---

## Failure Handling

### 1. B站 cookies not logged in

`IS_LOGIN=False`, `NAV_CODE=-101`

Reply: "B 站 cookies 当前不是登录态，API / AI 字幕可能不可用。请重新从已登录且能看到字幕的浏览器导出 Netscape 格式 cookies，覆盖服务器上的 /home/ubuntu/projects/bili_sub/bilibili.txt。"

### 2. Subtitle API failed, fallback to audio

`[warn] Bilibili API subtitle path failed, fallback to audio` — normal behavior, not a failure. Check downstream Groq/DeepSeek.

### 3. yt-dlp download failure

Check recent logs:

```bash
ls -lt /home/ubuntu/projects/bili_sub/logs | head
tail -n 120 /home/ubuntu/projects/bili_sub/logs/<latest log>
```

Common causes: B站 CDN disconnection, expired cookies, network flakiness, abnormal video link, B站 rate limiting.

Retry once:

```bash
cd /home/ubuntu/projects/bili_sub
./run_bili_sub.sh "<B站视频链接>"
```

### 4. Groq failure (transcribe stage)

Check proxy:

```bash
systemctl --user status mihomo.service --no-pager -l
ss -lntp | grep 7890
```

Groq should route through: `GROQ_PROXY_URL="http://127.0.0.1:7890"`

### 5. DeepSeek failure (summary stage)

Retry summarization only:

```bash
cd /home/ubuntu/projects/bili_sub
source .venv/bin/activate
python bili_groq.py --summarize-file "<RESULT_TXT路径>"
```

---

## Operational Notes

- Do NOT edit `keys.config` without user consent.
- Do NOT restart mihomo.
- Do NOT delete `output/`.
- Do NOT paste cookies, API keys, or proxy info into chat.
- Default workflow: `./run_bili_sub.sh "<URL>"` — do not call underlying Python commands directly unless troubleshooting.

---

## Variations

### Subtitle-only (no summary)

When user says "只帮我拉字幕，不用总结":

```bash
cd /home/ubuntu/projects/bili_sub
source .venv/bin/activate
python bili_groq.py "https://www.bilibili.com/video/BVxxxx" --download-only --pdf
```

### Check B站 cookies

When user asks "检查一下 B 站 cookies 还有效吗":

```bash
cd /home/ubuntu/projects/bili_sub
source .venv/bin/activate
python bili_groq.py --check-bilibili-login --require-login
```

---

## Current Known Limitations

1. B站 API / AI subtitles require valid logged-in cookies.
2. Some AI subtitle timelines are abnormal and may be rejected, falling back to audio transcription.
3. yt-dlp B站 audio downloads occasionally disconnect; the wrapper has staged retry.
4. Groq may return 403 on direct connection — must route through mihomo proxy.
5. DeepSeek occasionally has connection interruptions; the script has built-in retry.
