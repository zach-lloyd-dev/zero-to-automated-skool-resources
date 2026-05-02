# Notice

`/zta-watch` is a fork of the open-source `/watch` skill by Bradley Bonanno (`bradautomates`), released under the MIT License.

- Original repo: https://github.com/bradautomates/claude-video
- Original copyright: Copyright (c) 2026 Bradley Bonanno

Brad solved the hard part — figuring out that you can give Claude a video by combining `yt-dlp`, `ffmpeg`, and Whisper. We took that and built ZTA's version on top of it.

## What we changed

1. **Frame-diff dedupe** — hybrid scene-detection + heartbeat select filter in `frames.py`. Cuts frame count ~50-70% on talking-head content while keeping a guaranteed temporal floor. Inspired by the YouTube comment thread under Brad's launch video (`@D3ADLOLO` / `@MrMiguelChaves`).
2. **`--save` flag** — auto-writes the watch report to your Z Brain second brain (Obsidian-friendly markdown with frontmatter + tags) so it's searchable later.
3. **`--hook` preset** — one-flag shortcut for competitor hook analysis (first 30s, dense frames, structured analysis prompt).
4. **`--estimate-cost` flag** — prints expected token + Whisper cost before processing.
5. **`--no-dedupe` flag** — disables our scene-diff and falls back to the original fixed-fps behavior, for parity / debugging.
6. **Branding + paths** — `~/.config/zta-watch/.env` (separate from Brad's `~/.config/watch/`) so members can install both side-by-side. UA strings, command name, docs all rebranded for ZTA.

The `LICENSE` file preserves both copyright lines, as MIT requires.

If `/watch` is what you want straight from the source, install Brad's version: `https://github.com/bradautomates/claude-video`.
