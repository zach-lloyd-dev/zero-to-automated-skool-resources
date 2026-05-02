#!/usr/bin/env python3
"""/zta-watch entry point: download → extract frames → transcribe → report.

Prints a markdown report to stdout listing frame paths + transcript. Claude
then Reads each frame path to see the video.

Adds the following over the original /watch contract:
  --no-dedupe              disable hybrid scene-diff frame extraction
  --scene-threshold N      tune scene-diff sensitivity (default 0.10)
  --hook                   competitor hook-analysis preset (first 30s, dense)
  --save                   also save report to Z Brain second brain
  --estimate-cost          print expected token + Whisper cost and exit
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from download import download, is_url  # noqa: E402
from frames import (  # noqa: E402
    DEFAULT_SCENE_THRESHOLD,
    MAX_FPS,
    auto_fps,
    auto_fps_focus,
    extract,
    format_time,
    get_metadata,
    parse_time,
)
from save_to_zbrain import save_report, zbrain_root  # noqa: E402
from transcribe import filter_range, format_transcript, parse_vtt  # noqa: E402
from whisper import load_api_key, transcribe_video  # noqa: E402


# Token cost approximations for the cost estimator.
TOKENS_PER_FRAME_512 = 700
TOKENS_PER_FRAME_1024 = 2800
SONNET_INPUT_PER_1M = 3.0  # USD
GROQ_WHISPER_PER_HOUR = 0.05
OPENAI_WHISPER_PER_HOUR = 0.36


HOOK_ANALYSIS_LENS = """
## Hook Analysis Lens

Use the frames + transcript above to answer:

1. **Visual setup (0:00-0:03)** — what's on screen in the first 3 seconds? (subject, framing, on-screen text, color, motion)
2. **Verbal hook** — quote the literal opening words. Where does the first complete thought land?
3. **Pattern interrupt** — at what timestamp does something change? (cut, zoom, callout, voice shift) Cite the frame index.
4. **Implied promise** — why would a viewer keep watching? What's the unanswered question?
5. **Hook structure** — map setup → tension → payoff to specific timestamps.
6. **What's reusable** — name 1 mechanic worth stealing for ZTA / BSS content.
"""


def _hook_preset_override(args: argparse.Namespace) -> None:
    """Apply --hook preset defaults unless the user already specified them."""
    if args.start is None:
        args.start = "0"
    if args.end is None:
        args.end = "30"
    if args.resolution == 512:
        args.resolution = 1024
    if args.max_frames == 80:
        args.max_frames = 60


def _estimate_cost(
    duration_sec: float,
    frame_count: int,
    resolution: int,
    has_whisper_key: bool,
    backend: str | None,
    captions_likely: bool,
) -> str:
    tokens_per_frame = TOKENS_PER_FRAME_1024 if resolution >= 1024 else TOKENS_PER_FRAME_512
    image_tokens = frame_count * tokens_per_frame
    image_cost = image_tokens / 1_000_000 * SONNET_INPUT_PER_1M

    duration_hours = duration_sec / 3600
    whisper_cost_groq = duration_hours * GROQ_WHISPER_PER_HOUR
    whisper_cost_openai = duration_hours * OPENAI_WHISPER_PER_HOUR

    whisper_line = ""
    if captions_likely:
        whisper_line = f"  Whisper:        free (captions likely) — fallback ~${whisper_cost_groq:.3f} (Groq) / ${whisper_cost_openai:.2f} (OpenAI)"
    else:
        if backend == "openai":
            whisper_line = f"  Whisper:        ~${whisper_cost_openai:.2f} (OpenAI)"
        else:
            whisper_line = f"  Whisper:        ~${whisper_cost_groq:.3f} (Groq)"

    total_low = image_cost + (0 if captions_likely else whisper_cost_groq)
    total_high = image_cost * 1.5 + whisper_cost_groq

    return (
        f"  Duration:       {format_time(duration_sec)} ({duration_sec:.1f}s)\n"
        f"  Frames:         ~{frame_count} @ {resolution}px ≈ {image_tokens:,} input tokens\n"
        f"  Frame cost:     ~${image_cost:.3f} on Sonnet 4.5\n"
        f"{whisper_line}\n"
        f"  Estimated total: ~${total_low:.2f}-${total_high:.2f}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="zta-watch",
        description="Download a video, extract scene-diffed frames, surface the transcript.",
    )
    ap.add_argument("source", help="Video URL or local file path")
    ap.add_argument("--max-frames", type=int, default=80, help="Cap on frame count (default 80, hard max 100)")
    ap.add_argument("--resolution", type=int, default=512, help="Frame width in pixels (default 512)")
    ap.add_argument("--fps", type=float, default=None, help="Override auto-fps")
    ap.add_argument("--start", type=str, default=None, help="Range start (SS, MM:SS, or HH:MM:SS)")
    ap.add_argument("--end", type=str, default=None, help="Range end (SS, MM:SS, or HH:MM:SS)")
    ap.add_argument("--out-dir", type=str, default=None, help="Working directory (default: tmp)")
    ap.add_argument("--no-whisper", action="store_true", help="Disable Whisper fallback. Frames-only if no captions.")
    ap.add_argument("--whisper", choices=["groq", "openai"], default=None, help="Force a specific Whisper backend.")
    ap.add_argument("--no-dedupe", action="store_true", help="Disable scene-diff dedupe (legacy fixed-fps mode)")
    ap.add_argument(
        "--scene-threshold",
        type=float,
        default=DEFAULT_SCENE_THRESHOLD,
        help=f"Scene-diff sensitivity 0-1 (default {DEFAULT_SCENE_THRESHOLD}, lower = more frames)",
    )
    ap.add_argument("--hook", action="store_true", help="Hook-analysis preset (first 30s, dense, structured prompt)")
    ap.add_argument("--save", action="store_true", help="Save report to Z Brain (02_reference/video-watches/)")
    ap.add_argument("--estimate-cost", action="store_true", help="Print expected cost and exit (no processing)")
    args = ap.parse_args()

    if args.hook:
        _hook_preset_override(args)

    max_frames = min(args.max_frames, 100)
    dedupe = not args.no_dedupe

    if args.out_dir:
        work = Path(args.out_dir).expanduser().resolve()
    else:
        work = Path(tempfile.mkdtemp(prefix="zta-watch-"))
    work.mkdir(parents=True, exist_ok=True)

    # Cost estimate path: probe duration cheaply, print, exit.
    if args.estimate_cost:
        print(f"[zta-watch] estimating cost for: {args.source}", file=sys.stderr)
        if is_url(args.source):
            print("[zta-watch] note: URL duration estimation requires a partial download — skipping; estimate uses 5min default", file=sys.stderr)
            duration = 300.0
        else:
            meta = get_metadata(args.source)
            duration = meta["duration_seconds"]
        start_sec = parse_time(args.start)
        end_sec = parse_time(args.end)
        eff_dur = (end_sec or duration) - (start_sec or 0)
        focused = start_sec is not None or end_sec is not None
        fps, target = (auto_fps_focus if focused else auto_fps)(eff_dur, max_frames=max_frames)
        # Rough dedupe estimate: assume ~50% reduction on average content.
        est_frames = int(target * 0.5) if dedupe else target
        backend, _ = load_api_key(args.whisper)
        captions_likely = is_url(args.source) and not args.no_whisper
        print(_estimate_cost(eff_dur, est_frames, args.resolution, backend is not None, backend, captions_likely))
        return 0

    print(f"[zta-watch] working dir: {work}", file=sys.stderr)
    print(
        "[zta-watch] downloading via yt-dlp…" if is_url(args.source) else "[zta-watch] using local file…",
        file=sys.stderr,
    )
    dl = download(args.source, work / "download")
    video_path = dl["video_path"]

    meta = get_metadata(video_path)
    full_duration = meta["duration_seconds"]

    start_sec = parse_time(args.start)
    end_sec = parse_time(args.end)

    if start_sec is not None and start_sec < 0:
        raise SystemExit("--start must be non-negative")
    if end_sec is not None and start_sec is not None and end_sec <= start_sec:
        raise SystemExit("--end must be greater than --start")
    if full_duration > 0 and start_sec is not None and start_sec >= full_duration:
        raise SystemExit(f"--start {start_sec:.1f}s is past end of video ({full_duration:.1f}s)")

    # Clamp --end past video duration so frame budgets and dedupe stats reflect
    # actual processed duration, not the user's requested window. Common with
    # --hook (always --end 30) on videos shorter than 30s.
    if end_sec is not None and full_duration > 0 and end_sec > full_duration:
        end_sec = full_duration

    effective_start = start_sec if start_sec is not None else 0.0
    effective_end = end_sec if end_sec is not None else full_duration
    effective_duration = max(0.0, effective_end - effective_start)
    focused = start_sec is not None or end_sec is not None

    if focused:
        fps, target = auto_fps_focus(effective_duration, max_frames=max_frames)
    else:
        fps, target = auto_fps(effective_duration, max_frames=max_frames)
    if args.fps is not None:
        fps = min(args.fps, MAX_FPS)
        target = max(1, int(round(fps * effective_duration)))

    scope = (
        f"{format_time(effective_start)}-{format_time(effective_end)} ({effective_duration:.1f}s)"
        if focused else f"full {effective_duration:.1f}s"
    )
    mode_label = f"scene-diff (threshold {args.scene_threshold})" if dedupe else "fixed-fps (legacy)"
    print(f"[zta-watch] extracting up to {target} frames at {fps:.3f} fps over {scope} — {mode_label}…", file=sys.stderr)

    extraction = extract(
        video_path,
        work / "frames",
        fps=fps,
        resolution=args.resolution,
        max_frames=max_frames,
        start_seconds=start_sec,
        end_seconds=end_sec,
        dedupe=dedupe,
        scene_threshold=args.scene_threshold,
    )
    frames = extraction["frames"]

    transcript_segments: list[dict] = []
    transcript_text: str | None = None
    transcript_source: str | None = None
    if dl.get("subtitle_path"):
        try:
            all_segments = parse_vtt(dl["subtitle_path"])
            transcript_segments = filter_range(all_segments, start_sec, end_sec) if focused else all_segments
            transcript_text = format_transcript(transcript_segments)
            transcript_source = "captions"
        except Exception as exc:
            print(f"[zta-watch] subtitle parse failed: {exc}", file=sys.stderr)

    if not transcript_segments and not args.no_whisper:
        backend, api_key = load_api_key(args.whisper)
        if backend and api_key:
            try:
                all_segments, used_backend = transcribe_video(
                    video_path,
                    work / "audio.mp3",
                    backend=backend,
                    api_key=api_key,
                )
                transcript_segments = filter_range(all_segments, start_sec, end_sec) if focused else all_segments
                transcript_text = format_transcript(transcript_segments)
                transcript_source = f"whisper-{used_backend}"
            except SystemExit as exc:
                print(f"[zta-watch] whisper fallback failed: {exc}", file=sys.stderr)
        else:
            hint = (
                f"--whisper {args.whisper} was set but the matching API key is missing"
                if args.whisper else
                "no subtitles and no Whisper API key found"
            )
            setup_py = SCRIPT_DIR / "setup.py"
            print(
                f"[zta-watch] {hint} — run `python3 {setup_py}` to enable the Whisper fallback",
                file=sys.stderr,
            )

    info = dl.get("info") or {}

    # Build the report markdown into a buffer so we can also save it.
    lines: list[str] = []
    lines.append("# zta-watch: video report")
    lines.append("")
    lines.append(f"- **Source:** {args.source}")
    if info.get("title"):
        lines.append(f"- **Title:** {info['title']}")
    if info.get("uploader"):
        lines.append(f"- **Uploader:** {info['uploader']}")
    lines.append(f"- **Duration:** {format_time(full_duration)} ({full_duration:.1f}s)")
    if focused:
        lines.append(
            f"- **Focus range:** {format_time(effective_start)} → {format_time(effective_end)} "
            f"({effective_duration:.1f}s)"
        )
    if meta.get("width") and meta.get("height"):
        lines.append(f"- **Resolution:** {meta['width']}x{meta['height']} ({meta.get('codec') or 'unknown codec'})")
    mode = "focused" if focused else "full"

    if dedupe:
        lines.append(
            f"- **Frames:** {extraction['frames_emitted']} emitted, "
            f"{extraction['frames_deduped']} deduped "
            f"({extraction['savings_pct']}% savings via scene-diff @ {args.scene_threshold})"
        )
    else:
        lines.append(
            f"- **Frames:** {extraction['frames_emitted']} @ {fps:.3f} fps, "
            f"{mode} mode (legacy fixed-fps, dedupe disabled)"
        )
    lines.append(f"- **Frame size:** {args.resolution}px wide")
    if transcript_segments:
        in_range = " in range" if focused else ""
        lines.append(
            f"- **Transcript:** {len(transcript_segments)} segments{in_range} "
            f"(via {transcript_source or 'captions'})"
        )
    else:
        lines.append("- **Transcript:** none available")

    if not focused and full_duration > 600:
        mins = int(full_duration // 60)
        lines.append("")
        lines.append(
            f"> **Warning:** This is a {mins}-minute video. Even with scene-diff dedupe, "
            f"frame coverage is sparse on long videos. For tighter focus, "
            "re-run with `--start HH:MM:SS --end HH:MM:SS` or use `--hook` for the opening 30s."
        )

    lines.append("")
    lines.append("## Frames")
    lines.append("")
    lines.append(f"Frames live at: `{work / 'frames'}`")
    lines.append("")
    lines.append(
        "**Read each frame path below with the Read tool to view the image.** "
        "Frames are in chronological order; `t=MM:SS` is the absolute timestamp in the source video."
    )
    lines.append("")
    for frame in frames:
        lines.append(f"- `{frame['path']}` (t={format_time(frame['timestamp_seconds'])})")

    lines.append("")
    lines.append("## Transcript")
    lines.append("")
    if transcript_text:
        label = transcript_source or "captions"
        if focused:
            lines.append(f"_Source: {label}. Filtered to {format_time(effective_start)} → {format_time(effective_end)}:_")
        else:
            lines.append(f"_Source: {label}._")
        lines.append("")
        lines.append("```")
        lines.append(transcript_text)
        lines.append("```")
    elif focused and dl.get("subtitle_path"):
        lines.append(f"_No transcript lines fell inside {format_time(effective_start)} → {format_time(effective_end)}._")
    else:
        setup_py = SCRIPT_DIR / "setup.py"
        lines.append(
            "_No transcript available — proceed with frames only. "
            "Captions were missing and the Whisper fallback was unavailable "
            "(no API key set, or `--no-whisper` was used). "
            f"Run `python3 {setup_py}` to enable Whisper, then re-run._"
        )

    if args.hook:
        lines.append("")
        lines.append(HOOK_ANALYSIS_LENS)

    lines.append("")
    lines.append("---")
    lines.append(f"_Work dir: `{work}` — delete when done._")

    report_md = "\n".join(lines)
    print()
    print(report_md)

    if args.save:
        # Strip the work-dir line and frame absolute paths so the saved copy
        # remains useful after cleanup.
        body_for_save = report_md
        saved_path = save_report(
            title=info.get("title") or args.source,
            source=args.source,
            duration_seconds=full_duration,
            uploader=info.get("uploader"),
            frames_emitted=extraction["frames_emitted"],
            frames_deduped=extraction["frames_deduped"],
            transcript_source=transcript_source,
            body_markdown=body_for_save,
        )
        if saved_path:
            print()
            print(f"_Saved to Z Brain: `{saved_path}`_")
        else:
            print()
            print(f"_--save requested but Z Brain not found at `{zbrain_root()}` (set $Z_BRAIN_PATH to override)._")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
