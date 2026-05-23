---
name: bili-sub-video-summary
description: Process Bilibili video links in Feishu — canonical URL normalization, subtitle extraction, audio transcription, prompt-profile summarization, PDF attachment, and Feishu doc creation. Trigger when users ask to "拉字幕", "转文字", "总结", "生成文档", or send a B站 video link with intent to process. Do NOT trigger for code discussion, environment debugging, or log checking.
---

# bili-sub-video-summary

Automate B站 video subtitle/transcription/summary workflow via `bili_sub` on the server.

The workflow supports:

1. B站短链解析为标准长链接
2. B站 API / AI 字幕提取
3. yt-dlp 可见字幕 fallback
4. 音频下载 + Groq Whisper 转写 fallback
5. DeepSeek 按 prompt profile 总结
6. 飞书文档创建与 PDF 附件上传

---

## Trigger Examples

- "总结这个 B 站视频：https://www.bilibili.com/video/BV..."
- "拉一下这个视频的字幕：https://b23.tv/..."
- "帮我转写并总结这个视频：<B站链接>"
- "用时政模板总结这个视频：<B站链接>"
- "用技术教程模板总结这个视频：<B站链接>"
- "用播客模板总结这个视频：<B站链接>"
- "用做菜模板总结这个视频：<B站链接>"
- "跑一下 bili_sub：<B站链接>"
- User sends a B站 link in Feishu group with intent to process subtitles/summary.

Do NOT trigger for:

- code review of `bili_sub`
- environment debugging
- log analysis
- prompt design discussion
- OpenClaw skill editing discussion

---

## Server Paths

| Item | Path |
|---|---|
| Project root | `/home/ubuntu/projects/bili_sub` |
| Main wrapper | `/home/ubuntu/projects/bili_sub/run_bili_sub.sh` |
| Python script | `/home/ubuntu/projects/bili_sub/bili_groq.py` |
| Config | `/home/ubuntu/projects/bili_sub/keys.config` |
| B站 cookies | `/home/ubuntu/projects/bili_sub/bilibili.txt` |
| Prompt dir | `/home/ubuntu/projects/bili_sub/prompts` |
| Output dir | `/home/ubuntu/projects/bili_sub/output` |
| Log dir | `/home/ubuntu/projects/bili_sub/logs` |

---

## Prompt Profiles

The server supports 5 prompt profiles:

| User wording | Prompt profile | Prompt file |
|---|---|---|
| 默认模板 / 通用模板 / general / default | `default` | `prompts/default.md` |
| 时政模板 / 新闻模板 / 国际 / 社会新闻 / 舆论分析 | `news_politics` | `prompts/news_politics.md` |
| 技术教程模板 / AI / 芯片 / 编程 / 工具使用 / 教程 | `tech_tutorial` | `prompts/tech_tutorial.md` |
| 播客模板 / 访谈 / 对谈 / 多人讨论 / 嘉宾 | `podcast` | `prompts/podcast.md` |
| 做菜模板 / 美食 / 菜谱 / 食谱 / 烹饪 | `cooking` | `prompts/cooking.md` |

### Prompt Selection Rule

1. If the user explicitly names a template, use the corresponding `--prompt-profile`.
2. If the user does not specify a template, do NOT guess. Omit `--prompt-profile`; the server will use the default prompt.
3. If the user says "自动判断模板", use only obvious wording in the user message. If still uncertain, use default.
4. Do not run an extra LLM classification step just to choose the prompt.
5. Do not infer prompt type by reading the full transcript unless the user explicitly asks for that extra step.

Examples:

```bash
./run_bili_sub.sh "<B站视频链接>"
./run_bili_sub.sh "<B站视频链接>" --prompt-profile default
./run_bili_sub.sh "<B站视频链接>" --prompt-profile news_politics
./run_bili_sub.sh "<B站视频链接>" --prompt-profile tech_tutorial
./run_bili_sub.sh "<B站视频链接>" --prompt-profile podcast
./run_bili_sub.sh "<B站视频链接>" --prompt-profile cooking
````

---

## Safety Rules

Do NOT output in replies:

* Groq API key
* DeepSeek API key
* B站 cookies / SESSDATA / bili_jct
* Proxy subscription URLs
* mihomo full config
* `keys.config` content

Safe to output:

* Video title
* UP主
* Canonical B站 video link
* Generated file paths
* Feishu doc link
* Brief error reason
* Log file path

---

## URL Handling

The user may send either a B站 long link or a short link.

Supported examples:

```text
https://b23.tv/xxxx
https://bili2233.cn/xxxx
https://www.bilibili.com/video/BVxxxx/
https://www.bilibili.com/video/BVxxxx/?p=2&spm_id_from=...
```

The script will normalize the URL at the beginning of the workflow:

```text
Original URL
→ resolve short URL if needed
→ extract BVID and page
→ canonical URL
```

Expected canonical format:

```text
https://www.bilibili.com/video/<BVID>/
```

If the video has page parameter:

```text
https://www.bilibili.com/video/<BVID>/?p=<page>
```

Important:

* Always pass the user-provided URL to `run_bili_sub.sh`.
* Do NOT manually rewrite short links in the skill.
* Do NOT use the short link in Feishu document metadata.
* Feishu document must use `RESULT_CANONICAL_URL`.
* If short-link resolution fails, the script may fall back internally, but the document should still prefer `RESULT_CANONICAL_URL` if available.

---

## Preflight Checks

Only run when the user explicitly asks to check the environment, or after consecutive failures.

### 1. Check B站 login status

```bash
cd /home/ubuntu/projects/bili_sub
source .venv/bin/activate
python bili_groq.py --check-bilibili-login --require-login
```

Expected:

```text
IS_LOGIN=True
```

Failure reply:

```text
B站 cookies 当前不是登录态，需要重新从已登录且能看到字幕的浏览器导出 bilibili.txt，并上传到服务器。
```

### 2. Check mihomo / Groq proxy

```bash
systemctl --user status mihomo.service --no-pager -l
ss -lntp | grep -E '7890|7891|9090'
```

Expected:

```text
mihomo.service active
127.0.0.1:7890 listening
```

---

## Main Command

Default command:

```bash
cd /home/ubuntu/projects/bili_sub
./run_bili_sub.sh "<B站视频链接>"
```

With prompt profile:

```bash
cd /home/ubuntu/projects/bili_sub
./run_bili_sub.sh "<B站视频链接>" --prompt-profile <profile>
```

Valid profiles:

```text
default
news_politics
tech_tutorial
podcast
cooking
```

### Command Selection Examples

User says:

```text
总结这个视频：https://b23.tv/xxxx
```

Run:

```bash
cd /home/ubuntu/projects/bili_sub
./run_bili_sub.sh "https://b23.tv/xxxx"
```

User says:

```text
用时政模板总结这个视频：https://b23.tv/xxxx
```

Run:

```bash
cd /home/ubuntu/projects/bili_sub
./run_bili_sub.sh "https://b23.tv/xxxx" --prompt-profile news_politics
```

User says:

```text
用技术教程模板总结这个视频：https://www.bilibili.com/video/BVxxxx/
```

Run:

```bash
cd /home/ubuntu/projects/bili_sub
./run_bili_sub.sh "https://www.bilibili.com/video/BVxxxx/" --prompt-profile tech_tutorial
```

User says:

```text
用播客模板总结这个视频：https://www.bilibili.com/video/BVxxxx/
```

Run:

```bash
cd /home/ubuntu/projects/bili_sub
./run_bili_sub.sh "https://www.bilibili.com/video/BVxxxx/" --prompt-profile podcast
```

User says:

```text
用做菜模板总结这个视频：https://b23.tv/xxxx
```

Run:

```bash
cd /home/ubuntu/projects/bili_sub
./run_bili_sub.sh "https://b23.tv/xxxx" --prompt-profile cooking
```

---

## Expected Flow

```text
1. Normalize URL
   - b23.tv / bili2233.cn short URL → canonical B站 long URL
   - long URL → clean canonical URL

2. Fetch video metadata
   - title
   - author
   - bvid
   - aid
   - cid
   - page
   - original_url
   - canonical_url

3. Try B站 API / AI subtitles

4. Try yt-dlp visible .srt subtitles

5. If subtitles fail:
   - low-bitrate audio download
   - Groq Whisper transcription

6. DeepSeek summarization
   - use selected prompt profile
   - inject current Beijing date context

7. Output machine-readable RESULT_* fields

8. Create Feishu doc
   - use RESULT metadata under title
   - insert summary.md content as-is
   - attach PDF
```

---

## Parse Output

Extract from script output:

```text
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

Key fields:

| Field                  | Usage                      |
| ---------------------- | -------------------------- |
| `RESULT_TITLE`         | Feishu doc title           |
| `RESULT_AUTHOR`        | UP主 metadata               |
| `RESULT_CANONICAL_URL` | 视频链接 metadata              |
| `RESULT_SUMMARY`       | Markdown summary body      |
| `RESULT_PDF`           | PDF attachment             |
| `RESULT_TXT`           | transcript file            |
| `RESULT_SRT`           | subtitle file if available |

Important:

* `RESULT_SUMMARY` is typically `/home/ubuntu/projects/bili_sub/output/<title>.summary.md`
* `UP主：` MUST use `RESULT_AUTHOR`
* `视频链接：` MUST use `RESULT_CANONICAL_URL`
* Do NOT parse UP主 or video link from DeepSeek summary content
* Do NOT guess metadata from the document title
* Do NOT use the original short link as the final video link if `RESULT_CANONICAL_URL` exists

---

## Create Feishu Doc

After successful processing:

1. Read `RESULT_SUMMARY` file content.
2. Create a Feishu doc as a sub-page under wiki node:

   * `EZ5FwoP2aiBVbnkyVSOcMyPSnYf`
3. Wiki space:

   * `ZgEcw6JqoiY1wekIMi1ccAv7n4g`
4. The wiki is named:

   * `B站视频总结`
5. Title format:

   * `<RESULT_TITLE> - 总结`
6. Under the title, write metadata from machine-readable output:

```markdown
UP主：<RESULT_AUTHOR>
视频链接：<RESULT_CANONICAL_URL>

---
```

7. Write the entire `summary.md` content as-is into the document body after the metadata.
8. Do not restructure, truncate, or reformat `summary.md`.
9. Never use DeepSeek summary text as the source for `UP主：` or `视频链接：`.
10. Use only `RESULT_AUTHOR` and `RESULT_CANONICAL_URL` for metadata.
11. Use `wiki_node` parameter when creating the doc.
12. Do NOT pass `wiki_space` when using `wiki_node`; the two are mutually exclusive.
13. Default required attachment:

    * Attach the PDF file from `RESULT_PDF`.
    * Use `feishu_doc_media`.
    * Copy the PDF to `/tmp/` first if needed.
    * Keep the original Chinese filename when copying to `/tmp/`.
    * Attach only PDF.
    * Do not attach txt, srt, summary.md, cookies, logs, or config files.
14. Reply with the Feishu doc link.

If `RESULT_AUTHOR` is empty:

```text
UP主：未获取到
```

If `RESULT_CANONICAL_URL` is empty:

```text
视频链接：未获取到
```

Do not invent missing metadata.

---

## Success Reply Template

After completion, reply:

```text
已完成这个 B 站视频的字幕/转写和总结。

飞书文档：<文档链接>

视频信息：
- 标题：<RESULT_TITLE>
- UP主：<RESULT_AUTHOR>
- 链接：<RESULT_CANONICAL_URL>

本次生成文件：
- TXT: <RESULT_TXT>
- SRT: <RESULT_SRT，如有>
- PDF: <RESULT_PDF，如有>
- Summary: <RESULT_SUMMARY>
```

---

## Failure Handling

### 1. B站 cookies not logged in

Signals:

```text
IS_LOGIN=False
NAV_CODE=-101
```

Reply:

```text
B站 cookies 当前不是登录态，API / AI 字幕可能不可用。请重新从已登录且能看到字幕的浏览器导出 Netscape 格式 cookies，覆盖服务器上的 /home/ubuntu/projects/bili_sub/bilibili.txt。
```

### 2. Short URL resolution warning

Signals:

```text
[warn] failed to resolve Bilibili short URL
```

This is not always fatal. Continue if downstream stages succeed.

If the final output lacks `RESULT_CANONICAL_URL`, tell the user:

```text
视频处理完成，但短链未能稳定解析为标准长链接，因此飞书文档中的视频链接可能缺失。建议下次直接发送 bilibili.com/video/BV... 长链接。
```

### 3. Subtitle API failed, fallback to audio

Signal:

```text
[warn] Bilibili API subtitle path failed, fallback to audio
```

This is normal behavior, not a failure. Check downstream Groq/DeepSeek.

### 4. yt-dlp download failure

Check recent logs:

```bash
ls -lt /home/ubuntu/projects/bili_sub/logs | head
tail -n 120 /home/ubuntu/projects/bili_sub/logs/<latest log>
```

Common causes:

* B站 CDN disconnection
* expired cookies
* network flakiness
* abnormal video link
* B站 rate limiting

Retry once with the same command.

If a prompt profile was used, keep the same profile:

```bash
cd /home/ubuntu/projects/bili_sub
./run_bili_sub.sh "<B站视频链接>" --prompt-profile <profile>
```

### 5. Groq failure

Check proxy:

```bash
systemctl --user status mihomo.service --no-pager -l
ss -lntp | grep 7890
```

Groq should route through:

```text
GROQ_PROXY_URL="http://127.0.0.1:7890"
```

Do not print `keys.config`.

### 6. DeepSeek failure

Retry summarization only.

Default prompt:

```bash
cd /home/ubuntu/projects/bili_sub
source .venv/bin/activate
python bili_groq.py --summarize-file "<RESULT_TXT路径>"
```

With prompt profile:

```bash
cd /home/ubuntu/projects/bili_sub
source .venv/bin/activate
python bili_groq.py --summarize-file "<RESULT_TXT路径>" --prompt-profile <profile>
```

Use the same profile that the user requested.

---

## Operational Notes

* Do NOT edit `keys.config` without user consent.
* Do NOT restart mihomo unless explicitly asked or repeated failures require it.
* Do NOT delete `output/`.
* Do NOT paste cookies, API keys, or proxy info into chat.
* Default workflow: use `./run_bili_sub.sh "<URL>"`.
* Do not call underlying Python commands directly unless troubleshooting.
* If user specified a prompt profile, preserve that profile in retries.
* If user did not specify a prompt profile, do not add one.

---

## Variations

### Subtitle-only, no summary

When user says:

```text
只帮我拉字幕，不用总结
```

Run:

```bash
cd /home/ubuntu/projects/bili_sub
source .venv/bin/activate
python bili_groq.py "<B站视频链接>" --download-only --pdf
```

This still normalizes short URLs and outputs metadata when available.

### Check B站 cookies

When user asks:

```text
检查一下 B站 cookies 还有效吗
```

Run:

```bash
cd /home/ubuntu/projects/bili_sub
source .venv/bin/activate
python bili_groq.py --check-bilibili-login --require-login
```

### Use a specific prompt

When user says:

```text
用做菜模板重新总结这个 TXT
```

Run:

```bash
cd /home/ubuntu/projects/bili_sub
source .venv/bin/activate
python bili_groq.py --summarize-file "<RESULT_TXT路径>" --prompt-profile cooking
```

---

## Current Known Limitations

1. B站 API / AI subtitles require valid logged-in cookies.
2. Some AI subtitle timelines are abnormal and may be rejected, falling back to audio transcription.
3. yt-dlp B站 audio downloads occasionally disconnect; the wrapper has staged retry.
4. Groq may return 403 on direct connection — must route through mihomo proxy.
5. DeepSeek occasionally has connection interruptions; the script has built-in retry.
6. Prompt profile selection is explicit-first. If the user does not specify a template, the workflow uses the default prompt rather than guessing.
7. Short-link resolution depends on B站 redirect behavior and network state; canonical URL is preferred whenever available.