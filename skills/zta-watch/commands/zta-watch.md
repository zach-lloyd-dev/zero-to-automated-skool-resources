---
description: Watch any video (URL or local path). Scene-diff frame extraction + captions/Whisper transcript. Add --hook for competitor analysis or --save to log to Z Brain.
argument-hint: <video-url-or-path> [question]
allowed-tools: [Bash, Read, AskUserQuestion]
---

Invoke the `zta-watch` skill (defined in SKILL.md) with the user's arguments: $ARGUMENTS

Follow the skill's full pipeline: preflight setup check → download via yt-dlp → extract scene-diffed frames at auto-scaled fps → pull captions or Whisper transcript → Read each frame → answer the user grounded in frames and transcript. If the user provided no arguments, ask for a video URL or local path before proceeding.

If the user's question maps to "what's the hook" / "how did they open" / "break down the opening," add `--hook` to the watch.py call. If the user asks for the cost up front, run with `--estimate-cost` first and report the estimate before processing.
