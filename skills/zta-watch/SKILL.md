---
name: zta-watch
description: Watch any video (URL or local path) — download with yt-dlp, extract scene-diffed frames with ffmpeg, pull captions or Whisper transcript, then answer questions grounded in what's actually on screen and in the audio.
argument-hint: "<video-url-or-path> [question]"
allowed-tools: Bash, Read, AskUserQuestion
license: MIT
user-invocable: true
---

# /zta-watch — give Claude the ability to watch a video

Claude has no native video input. This skill builds one out of three free, battle-tested tools running locally on the user's laptop: `yt-dlp` to download, `ffmpeg` to extract frames + audio, and (optionally) a Whisper API for transcripts when captions are unavailable. The skill prints a markdown report with frame paths and a timestamped transcript. You then `Read` each frame path to see the images and answer the user grounded in both the visuals and the words.

## Step 0 — Setup preflight (silent on success)

Before every `/zta-watch` run, verify dependencies and Whisper key:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py" --check
```

Exit 0 → proceed silently. Do not announce "setup is complete" — the user does not need a status message on every turn.

On non-zero exit:

| Exit | Meaning | Action |
|------|---------|--------|
| `2` | Missing binaries (`ffmpeg` / `ffprobe` / `yt-dlp`) | Run installer |
| `3` | No Whisper API key | Run installer to scaffold `.env`, then ask user for a key |
| `4` | Both missing | Run installer, then ask for a key |

The installer is idempotent:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py"
```

On macOS, it auto-installs `ffmpeg` and `yt-dlp` via Homebrew. Linux/Windows print exact commands. It scaffolds `~/.config/zta-watch/.env` (mode `0600`) with commented placeholders.

If a Whisper key is still missing after install, ask the user via `AskUserQuestion` whether they have a Groq key (preferred — cheap, fast, generous free tier) or an OpenAI key. Then write into `~/.config/zta-watch/.env`. If they don't want Whisper, proceed with `--no-whisper` and tell them videos without captions come back frames-only.

**Structured mode:** `setup.py --json` emits `{status, first_run, missing_binaries, whisper_backend, has_api_key, config_file, platform}` for branching.

Within a session, skip Step 0 on follow-up calls — once `--check` returned 0, nothing changes between turns.

## When to use

- User pastes a video URL (YouTube, Vimeo, X, TikTok, Loom, Twitch clip, most yt-dlp-supported sites) and asks about it.
- User points at a local video file (`.mp4`, `.mov`, `.mkv`, `.webm`, etc.) and asks about it.
- User types `/zta-watch <url-or-path> [question]`.

## Recommended limits

- **Best accuracy: under 10 minutes.** Frame coverage is denser on shorter videos. Even with scene-diff dedupe, a 30-min talking-head still gets sparser temporal sampling than a 5-min one.
- **Hard caps: 100 frames total, 2 fps.** Token cost grows linearly with frame count.
- For long videos, prefer `--start` / `--end` (focused mode) or `--hook` (first 30s preset) over a sparse full-video scan.

## How to invoke

**Step 1 — parse the user input.** Separate the source (URL or path) from any question. Example: `/zta-watch https://youtu.be/abc what's the hook?` → source = `https://youtu.be/abc`, question = `what's the hook?`.

**Step 2 — run the watch script.** Pass the source verbatim:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/watch.py" "<source>"
```

Optional flags:
- `--start T` / `--end T` — focus on a section. Accepts `SS`, `MM:SS`, or `HH:MM:SS`. Auto-scales denser frame budget.
- `--hook` — preset for competitor-content hook analysis (first 30s, 1024px, 60 frames, structured analysis prompt appended). Use this whenever the user asks "what's the hook" / "how did they open" / "break down the opening."
- `--max-frames N` — lower the cap for tighter token budget.
- `--resolution W` — frame width in px (default 512; bump to 1024 only if the user needs to read on-screen text like slides or terminals).
- `--fps F` — override auto-fps (clamped to 2 fps max).
- `--no-dedupe` — disable scene-diff (legacy fixed-fps behavior). Use only if the user explicitly asks for parity testing or the dedupe is misbehaving on a specific video.
- `--scene-threshold N` — tune scene-diff sensitivity (default 0.10, range 0-1; lower = more frames retained).
- `--whisper groq|openai` — force a specific Whisper backend (default: prefer Groq).
- `--no-whisper` — disable Whisper fallback entirely.
- `--out-dir DIR` — keep working files somewhere specific (default: tmp).
- `--save` — write the report to the user's Z Brain at `02_reference/video-watches/`. Honors `$Z_BRAIN_PATH`. No-ops gracefully if the path doesn't exist.
- `--estimate-cost` — print expected cost and exit (no actual processing). Use when the user asks "how much will this cost?" before running.

### Focusing on a section (denser frame budget)

When the user names a moment ("around 2:30", "the last 30 seconds", "from 0:45 to 1:00"), pass `--start` / `--end`. The script switches to focused-mode budgets (denser, capped at 2 fps). Transcript auto-filters to the same range; frame timestamps stay absolute.

### Hook analysis preset

If the user asks anything that maps to "what's the hook" / "how did they open" / "break down the opening," use `--hook`. It applies `--start 0 --end 30 --resolution 1024 --max-frames 60` and appends a structured Hook Analysis Lens to the report. Answer using that lens.

**Step 3 — Read every frame path the script lists.** The Read tool renders JPEGs as images. Read all frames in a single message (parallel tool calls) so you see them together. Frames are chronologically ordered; `t=MM:SS` is the absolute timestamp.

**Step 4 — answer the user.** You have two evidence streams:
- **Frames** — what's on screen at each timestamp.
- **Transcript** — what's said. Header shows source: `captions` (yt-dlp pulled native subs) or `whisper-groq` / `whisper-openai`.

Cite timestamps in your answer. If the user didn't ask a specific question, summarize the video — structure, key moments, notable visuals, spoken content.

If the report includes a Hook Analysis Lens (because `--hook` was used), answer using that lens.

**Step 5 — clean up.** The script prints a working directory at the end. If the user isn't going to ask follow-ups, delete it with `rm -rf <dir>`. If they might, leave it.

## Scene-diff frame extraction (default-on, what makes this skill different)

The default extractor uses an ffmpeg `select` filter that emits a frame only when one of the following is true:
- Scene score crosses the configured threshold (default 0.10), OR
- A heartbeat interval has elapsed since the last emitted frame (heartbeat = 1/fps so we still hit our budget on uniform content), OR
- It's the first frame.

Result: talking-head and slide-deck videos drop frame counts ~50-70% with no loss of meaningful information; demo videos and action content keep dense coverage. Frame-budget cap (`-frames:v {max_frames}`) still applies, so token cost is bounded.

Per-frame timestamps come from an ffmpeg `metadata=print` sidecar file (since deduped frames aren't evenly spaced). The report header shows the savings: `Frames: 18 emitted, 62 deduped (78% savings via scene-diff)`.

If the user asks why a frame they expected is missing, lower `--scene-threshold` (e.g. 0.05) or use `--no-dedupe` for parity with the legacy uniform-fps behavior.

## Z Brain integration (`--save`)

When `--save` is passed, the report is also written to `$Z_BRAIN_PATH/02_reference/video-watches/YYYY-MM-DD-{slug}.md` with Obsidian-friendly frontmatter (`title`, `source`, `duration`, `uploader`, `date_watched`, `frames_kept`, `frames_deduped`, `transcript_source`, `tags`). `bss-qmd refresh` will then index it for semantic search.

`Z_BRAIN_PATH` defaults to `~/Documents/Z Brain`. If the path doesn't exist, `--save` no-ops with a helpful message — non-BSS users won't get errors.

## Transcription

The script gets a timestamped transcript in one of two ways:

1. **Native captions (free, preferred).** yt-dlp pulls manual or auto-generated subtitles when the source supports them.
2. **Whisper API fallback.** If captions are missing, the script extracts mono 16 kHz audio (~0.5 MB/min) and uploads to whichever Whisper API has a key:
   - **Groq** — `whisper-large-v3`. Preferred default: cheap, fast, generous free tier. `console.groq.com/keys`.
   - **OpenAI** — `whisper-1`. Fallback. `platform.openai.com/api-keys`.

Both keys live in `~/.config/zta-watch/.env`. Override with `--whisper openai`. Use `--no-whisper` to skip the fallback.

## Failure modes and handling

- **Setup preflight failed** → run `python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py"`. For API key, ask via `AskUserQuestion` and write into `~/.config/zta-watch/.env`.
- **No transcript available** → captions missing AND (no Whisper key OR Whisper failed). Proceed frames-only and tell the user.
- **Long video warning** → acknowledge in your answer. Offer to re-run focused on a specific section via `--start`/`--end` or `--hook` for the opening.
- **Download fails** → yt-dlp's error goes to stderr. If login-required or region-locked, tell the user plainly; do not retry.
- **Whisper fails** → printed to stderr (likely: invalid key, rate limit, 25 MB upload limit on a long video). Report says "none available." Retry with the other backend if available, or `--no-whisper` to give up cleanly.
- **Scene-diff missed a frame the user wanted** → re-run with `--scene-threshold 0.05` (more permissive) or `--no-dedupe`.

## Token efficiency

Frames dominate the bill. Order of magnitude:
- 30 frames at 512px ≈ 20-25k image tokens.
- 80 frames at 1024px ≈ 220-280k image tokens.
- Transcript is cheap (a few thousand tokens for a 10-min video).

Default scene-diff brings most full-video runs to 20-50k image tokens. Use `--estimate-cost` first when running on something potentially expensive.

If you already watched a video this session, do **not** re-run the script — you have the frames and transcript in context. Answer from what you have.

## Security & Permissions

**What this skill does:**
- Runs `yt-dlp` locally to download the video and pull native captions (public data; request goes to whatever host the URL points at).
- Runs `ffmpeg` / `ffprobe` locally to extract frames as JPEGs and (when Whisper is needed) mono 16 kHz audio.
- Sends the extracted audio clip to Groq's Whisper API when `GROQ_API_KEY` is set (preferred).
- Sends the extracted audio clip to OpenAI's transcription API when `OPENAI_API_KEY` is set and Groq is not, or when `--whisper openai` is forced.
- Writes downloaded video, frames, audio, and intermediate transcript to a working directory under the system temp dir (or `--out-dir` if specified).
- Reads / creates `~/.config/zta-watch/.env` (mode `0600`) for Whisper key(s) and `SETUP_COMPLETE` marker. Also reads `.env` in the current working directory as fallback.
- When `--save` is passed: writes the report to `$Z_BRAIN_PATH/02_reference/video-watches/`.

**What this skill does NOT do:**
- Does not upload the video itself to any API — only extracted audio goes out, and only when captions are missing AND Whisper is enabled.
- Does not access any platform account (no login, no cookies, no posting).
- Does not share API keys between providers.
- Does not log, cache, or write API keys to stdout, stderr, or output files.
- Does not persist anything outside the working directory, the config file, and (with `--save`) the Z Brain video-watches folder.

**Bundled scripts:** `scripts/watch.py` (entry point), `scripts/download.py` (yt-dlp wrapper), `scripts/frames.py` (ffmpeg scene-diff extraction), `scripts/transcribe.py` (caption parsing), `scripts/whisper.py` (Groq / OpenAI clients), `scripts/setup.py` (preflight + installer), `scripts/save_to_zbrain.py` (Z Brain integration).

Inspired by `/watch` by Bradley Bonanno (`bradautomates`, MIT). See `NOTICE.md` for what's different.
