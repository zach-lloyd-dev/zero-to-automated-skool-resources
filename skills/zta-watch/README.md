# /zta-watch

**Give Claude the ability to actually watch any video.**

Paste a YouTube URL, a Loom, a TikTok, a screen recording — Claude downloads it, pulls the frames, grabs the transcript, and answers your question grounded in what's actually on screen and in the audio. Not a guess. Not a hallucination off the title. The frames are real, the transcript is real, and Claude treats them like a primary source.

```
/zta-watch https://youtu.be/dQw4w9WgXcQ what happens at the 30 second mark?
/zta-watch https://www.tiktok.com/@user/video/123 --hook
/zta-watch ~/Movies/screen-recording.mp4 when does the UI break?
/zta-watch https://vimeo.com/123 --save
```

## Why this exists

Claude can read a webpage, run a script, browse a repo. What it can't do out of the box is *watch* a video — and most of the interesting stuff in video isn't said out loud. It happens on screen.

If you do content for a living, you watch competitor videos to figure out what made them work — the visual setup, the pattern interrupt, the on-screen text in the first 3 seconds. That used to mean watching with a notepad. With `/zta-watch` you paste the URL, ask "what's the hook?" and Claude breaks it down by frame.

If you're a coach, a consultant, an automation builder — you watch screen recordings of clients getting stuck, demos of tools you're evaluating, podcasts you'd never have time to sit through. `/zta-watch` makes all of those one-paste-and-go.

## How it works

1. **You paste a video and a question.** URL (any of the ~1000+ sites yt-dlp supports) or a local path (`.mp4`, `.mov`, `.mkv`, `.webm`).
2. **`yt-dlp` downloads it** to a temp working directory. Local files don't get re-downloaded — just probed in place.
3. **`ffmpeg` extracts frames using scene-diff.** Instead of grabbing a frame every N seconds (which wastes tokens on talking-head content), zta-watch's extractor only emits a frame when the scene actually changes — with a guaranteed heartbeat so you never miss a long quiet section.
4. **Transcript comes from one of two places.** First try: `yt-dlp` pulls native captions (manual or auto-generated). Free, instant. Fallback: extract a mono 16 kHz audio clip and ship to Whisper — Groq's `whisper-large-v3` (preferred — cheap, fast, generous free tier) or OpenAI's `whisper-1`.
5. **Frames + transcript handed to Claude.** Frame paths print with `t=MM:SS` markers; transcript prints with timestamps. Claude `Read`s each frame in parallel — JPEGs render directly as images.
6. **Claude answers from what it actually saw and heard.** Not "based on the title." It saw the frames. It read the transcript. It answers the way someone who watched the video would.

## What's different from the original `/watch`

This is a fork of `/watch` by Bradley Bonanno (MIT licensed — see `LICENSE` and `NOTICE.md`). Brad solved the hard part. We added:

- **Scene-diff frame extraction (default-on).** Hybrid scene-detection + heartbeat select filter. Cuts frames ~50-70% on talking-head content with no loss of meaning. Demo videos and action content keep their dense coverage.
- **`--hook` preset.** One flag for competitor content research — first 30s, dense frames, structured hook-analysis prompt appended to the report.
- **`--save` flag.** Auto-writes the report to your Z Brain at `02_reference/video-watches/` with Obsidian-friendly frontmatter so it's searchable later via `bss-qmd`. No-ops gracefully if you don't have a Z Brain.
- **`--estimate-cost` flag.** Print expected token + Whisper cost before processing.
- **Separate config dir.** Lives at `~/.config/zta-watch/` so members can install both side-by-side with Brad's original.

If you want straight `/watch` from the source, install Brad's: `https://github.com/bradautomates/claude-video`.

## Install

This skill ships as part of the [Zero to Automated Skool Resources](https://github.com/zach-lloyd-dev/zero-to-automated-skool-resources) repo. Run the toolkit installer:

```bash
git clone https://github.com/zach-lloyd-dev/zero-to-automated-skool-resources.git
cd zero-to-automated-skool-resources
bash install.sh
```

The installer copies `zta-watch` into `~/.claude/skills/` alongside the other ZTA skills.

On first run, `/zta-watch` will:
- Auto-install `ffmpeg` + `yt-dlp` via Homebrew on macOS.
- Print the exact `apt` / `dnf` / `pipx` commands on Linux.
- Print the exact `winget` / `pip` commands on Windows.
- Scaffold `~/.config/zta-watch/.env` (mode `0600`) with placeholders for `GROQ_API_KEY` and `OPENAI_API_KEY`.

## Bring your own keys

Captions cover the majority of public videos for free — Whisper only kicks in for local files, TikToks without captions, and the occasional caption-less YouTube upload.

| Capability | What you need | Cost |
|------------|---------------|------|
| Download + native captions | `yt-dlp` + `ffmpeg` | Free |
| Whisper fallback (preferred) | [Groq API key](https://console.groq.com/keys) — `whisper-large-v3` | ~$0.05/hr (free tier covers most use) |
| Whisper fallback (alt) | [OpenAI API key](https://platform.openai.com/api-keys) — `whisper-1` | ~$0.36/hr |
| Disable Whisper entirely | `--no-whisper` | Free, frames-only when no captions |

## Usage

```
/zta-watch https://youtu.be/dQw4w9WgXcQ what happens at 30s?
/zta-watch https://www.tiktok.com/@user/video/123 --hook
/zta-watch ~/Movies/recording.mp4 when does the UI break?
/zta-watch https://vimeo.com/123 --save
```

Focused on a specific section:
```
/zta-watch https://youtu.be/abc --start 2:15 --end 2:45
/zta-watch video.mp4 --start 50 --end 60
/zta-watch "$URL" --start 1:12:00            # from 1h12m to end
```

Other knobs (passed to `scripts/watch.py`):

- `--max-frames N` — lower the cap for tighter token budget.
- `--resolution W` — bump frame width to 1024 px when reading on-screen text (slides, terminals, code).
- `--fps F` — override the auto-fps calculation (still capped at 2 fps).
- `--scene-threshold N` — tune scene-diff sensitivity (default 0.10; lower = more frames retained).
- `--no-dedupe` — disable scene-diff (legacy fixed-fps behavior).
- `--whisper groq|openai` — force a specific Whisper backend.
- `--no-whisper` — disable transcription entirely; frames only.
- `--out-dir DIR` — keep working files somewhere specific (default: tmp).
- `--save` — also write the report to `$Z_BRAIN_PATH/02_reference/video-watches/`.
- `--estimate-cost` — print expected cost and exit (no processing).

## Limits

- **Best accuracy: under 10 minutes.** Past that, even with scene-diff, coverage gets sparser. Use `--start`/`--end` to focus.
- **Hard caps: 2 fps, 100 frames.** Frame count drives token cost.
- **Whisper upload limit: 25 MB.** At mono 16 kHz that's about 50 minutes of audio. Longer videos need either captions or a smaller window via `--start`/`--end`.
- **No private platforms.** This skill doesn't log into anything. Public URLs and local files only.

## Structure

```
.
├── SKILL.md                  # skill contract — what Claude reads
├── README.md                 # this file
├── NOTICE.md                 # attribution + what we changed vs Brad's
├── LICENSE                   # MIT, preserves original copyright
├── commands/
│   └── zta-watch.md          # slash command shim
└── scripts/
    ├── watch.py              # entry point — orchestrates the pipeline
    ├── download.py           # yt-dlp wrapper
    ├── frames.py             # ffmpeg scene-diff extraction + auto-fps
    ├── transcribe.py         # VTT parsing + dedupe
    ├── whisper.py            # Groq / OpenAI clients (pure stdlib)
    ├── setup.py              # preflight + installer
    └── save_to_zbrain.py     # --save flag implementation
```

## Open source

MIT licensed. See `LICENSE` and `NOTICE.md`.

Built on `yt-dlp`, `ffmpeg`, and Claude's multimodal `Read` tool. Whisper transcription via [Groq](https://groq.com) or [OpenAI](https://openai.com).
