---
name: check-bili-updates
description: Check followed Bilibili UP creators for new videos using the local bili_sub update checker, then return the generated updates.md result.
metadata: {"openclaw":{"os":["linux"],"requires":{"bins":["bash","python"]}}}
---

# check-bili-updates Skill

This skill checks whether the user's followed Bilibili UP creators have published new videos.

It runs the local `check_bili_updates.py` script inside the `bili_sub` project, then reads and summarizes the generated `updates.md`.

Current scope:

- Check followed Bilibili UP updates
- Read `updates.md`
- Reply with new video candidates
- Do not automatically run the downstream subtitle or summarization flow

---

## When to use this skill

Use this skill when the user asks things like:

- 检查一下 B站 UP 主有没有更新
- 看看 B站有没有新视频
- 跑一下 B站更新检查
- 查一下关注的 UP 有没有更新
- 今天 B站关注的 UP 有更新吗
- 本周 B站关注的 UP 更新了哪些视频
- check Bilibili updates
- check followed UP updates

---

## Project paths

The project root is:

```bash
/home/ubuntu/projects/bili_sub
```

The update checker script is:

```bash
/home/ubuntu/projects/bili_sub/check_bili_updates/check_bili_updates.py
```

The generated output file is:

```bash
/home/ubuntu/projects/bili_sub/check_bili_updates/updates.md
```

The virtual environment is:

```bash
/home/ubuntu/projects/bili_sub/.venv
```

The UP list config is:

```bash
/home/ubuntu/projects/bili_sub/check_bili_updates/up_list.yaml
```

The seen history file is:

```bash
/home/ubuntu/projects/bili_sub/check_bili_updates/seen_videos.json
```

---

## Normal update check

When the user asks to check Bilibili updates, run:

```bash
cd /home/ubuntu/projects/bili_sub
source .venv/bin/activate
python check_bili_updates/check_bili_updates.py
```

Then read:

```bash
cat /home/ubuntu/projects/bili_sub/check_bili_updates/updates.md
```

Reply to the user based only on the contents of `updates.md`.

---

## Reset test mode

Only when the user explicitly asks to reset history, test from scratch, or force recheck recent videos, run:

```bash
cd /home/ubuntu/projects/bili_sub
source .venv/bin/activate
python check_bili_updates/check_bili_updates.py --reset-seen
```

Then read:

```bash
cat /home/ubuntu/projects/bili_sub/check_bili_updates/updates.md
```

Important:

- Do not use `--reset-seen` for normal checks.
- `--reset-seen` rewrites the seen history and should only be used for testing or explicit reset requests.

---

## Reply rules

When replying:

1. Use `updates.md` as the source of truth.
2. Do not invent video titles, links, BVIDs, UP names, descriptions, or timestamps.
3. If no new videos were found, say so clearly.
4. If new videos were found, include:
   - title
   - UP name
   - published time if available
   - video link
   - BVID
   - description if available
5. If some UP creators failed, include the failed UP section.
6. Keep the reply concise.
7. Do not automatically run the downstream `bili_sub` subtitle/transcription/summarization flow.
8. Let the user manually choose which video link should be processed next.

---

## Expected updates.md format

The output file may look like this:

```markdown
# B站 UP 主更新检查

检查时间：YYYY-MM-DD HH:MM:SS

本次发现 N 个新视频。

## 视频标题

- UP主：xxx
- 发布时间：YYYY-MM-DD HH:MM:SS
- 链接：https://www.bilibili.com/video/BVxxxxxx
- BVID：BVxxxxxx

简介：

视频简介内容
```

Or:

```markdown
# B站 UP 主更新检查

检查时间：YYYY-MM-DD HH:MM:SS

本次没有发现新视频。
```

---

## Weekly review request

If the user asks questions like:

- 本周关注的 UP 更新了哪些视频
- 回溯一下本周 B站更新
- 查一下最近一周 seen_videos.json 里有哪些新视频

Then inspect:

```bash
cat /home/ubuntu/projects/bili_sub/check_bili_updates/seen_videos.json
```

The current `seen_videos.json` stores video metadata, including fields such as:

- `bvid`
- `title`
- `url`
- `published_at`
- `up_name`
- `first_seen_at`

Use `published_at` or `first_seen_at` to summarize recent videos.

If the user does not specify whether to use video publish time or discovery time, prefer `published_at` for “视频本身本周发布”，and prefer `first_seen_at` for “本周脚本发现的新视频”.

Do not modify `seen_videos.json` during a review request.

---

## Failure handling

If the update command fails, report the actual error.

Useful diagnosis commands:

```bash
cd /home/ubuntu/projects/bili_sub
source .venv/bin/activate
python -m yt_dlp --version
python check_bili_updates/check_bili_updates.py
```

If `yt-dlp` is missing, suggest:

```bash
cd /home/ubuntu/projects/bili_sub
source .venv/bin/activate
pip install -U yt-dlp
```

If `pyyaml` is missing, suggest:

```bash
cd /home/ubuntu/projects/bili_sub
source .venv/bin/activate
pip install -U pyyaml
```

If `up_list.yaml` is missing or invalid, tell the user to check:

```bash
/home/ubuntu/projects/bili_sub/check_bili_updates/up_list.yaml
```

---

## Boundaries

Do not run downstream processing unless the user explicitly gives a video link and asks to process it.

Do not run commands like this automatically:

```bash
./auto_sub.sh <video_url>
```

or:

```bash
python main.py <video_url>
```

This skill currently only checks Bilibili updates and reports candidate video links.

The downstream subtitle, transcription, and summarization workflow will be added later as a separate capability.