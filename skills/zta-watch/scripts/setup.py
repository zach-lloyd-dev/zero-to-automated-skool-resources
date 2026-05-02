#!/usr/bin/env python3
"""Setup / preflight for /zta-watch.

Modes:
  setup.py --check      Silent preflight. Exit 0 if ready, 2/3/4 on failure.
  setup.py --json       Machine-readable status for Claude to parse.
  setup.py              Installer. Auto-installs deps, scaffolds .env, marks SETUP_COMPLETE.

Design:
- Silent on success: --check exits 0 with no output when ready so /zta-watch
  doesn't spam status messages on every turn.
- Idempotent: re-running the installer is safe — it never clobbers existing
  keys and only appends missing ones.
- SETUP_COMPLETE=true in ~/.config/zta-watch/.env tells us the user has been
  through a successful installer run at least once.
- Never sudo. On macOS, auto-install via brew. Elsewhere, print exact commands.
- Never write an API key to disk automatically — only scaffold placeholders.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


REQUIRED_BINARIES = ["ffmpeg", "ffprobe", "yt-dlp"]
YTDLP_STALE_DAYS = 60  # YouTube format extractors break ~quarterly; 60d is conservative.
CONFIG_DIR = Path.home() / ".config" / "zta-watch"
CONFIG_FILE = CONFIG_DIR / ".env"
ENV_TEMPLATE = """# /zta-watch API configuration
#
# Whisper transcription fallback — used only when yt-dlp cannot get captions
# (or when you point /zta-watch at a local file with no subtitles).
#
# Groq is preferred: it runs whisper-large-v3 at a fraction of OpenAI's price
# and is faster in practice. Their free tier covers ~99% of normal usage.
# OpenAI is the compatible fallback.
#
# Get a Groq key:    https://console.groq.com/keys
# Get an OpenAI key: https://platform.openai.com/api-keys
#
# Leave both blank to disable Whisper — /zta-watch will still work, but videos
# without native captions will come back frames-only.

GROQ_API_KEY=
OPENAI_API_KEY=
"""


def _which(name: str) -> str | None:
    return shutil.which(name)


def _check_binaries() -> list[str]:
    return [b for b in REQUIRED_BINARIES if not _which(b)]


def _check_ytdlp_stale() -> tuple[bool, str | None]:
    """Return (is_stale, version). Stale yt-dlp gets 403'd by YouTube SABR."""
    if _which("yt-dlp") is None:
        return False, None
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"], capture_output=True, text=True, timeout=5
        )
        version = result.stdout.strip()
        parts = version.split(".")
        if len(parts) != 3:
            return False, version
        v_date = dt.date(int(parts[0]), int(parts[1]), int(parts[2]))
        days_old = (dt.date.today() - v_date).days
        return days_old > YTDLP_STALE_DAYS, version
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return False, None


def _check_file_permissions(path: Path) -> None:
    """Warn to stderr if a secrets file is world/group readable."""
    try:
        mode = path.stat().st_mode
        if mode & 0o044:
            sys.stderr.write(
                f"[zta-watch] WARNING: {path} is readable by other users. "
                f"Run: chmod 600 {path}\n"
            )
            sys.stderr.flush()
    except OSError:
        pass


def _read_env_key(name: str) -> str | None:
    value = os.environ.get(name)
    if value and value.strip():
        return value.strip()
    if not CONFIG_FILE.exists():
        return None
    _check_file_permissions(CONFIG_FILE)
    try:
        for line in CONFIG_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, raw = line.partition("=")
            if key.strip() != name:
                continue
            raw = raw.strip()
            if len(raw) >= 2 and raw[0] in ('"', "'") and raw[-1] == raw[0]:
                raw = raw[1:-1]
            return raw or None
    except OSError:
        return None
    return None


def _have_api_key() -> tuple[bool, str | None]:
    if _read_env_key("GROQ_API_KEY"):
        return True, "groq"
    if _read_env_key("OPENAI_API_KEY"):
        return True, "openai"
    return False, None


def is_first_run() -> bool:
    """True if the installer hasn't completed successfully yet."""
    return _read_env_key("SETUP_COMPLETE") != "true"


def _scaffold_env() -> bool:
    if CONFIG_FILE.exists():
        return False
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(ENV_TEMPLATE)
    try:
        CONFIG_FILE.chmod(0o600)
    except OSError:
        pass
    return True


def _write_setup_complete() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    existing = ""
    if CONFIG_FILE.exists():
        existing = CONFIG_FILE.read_text()
        for line in existing.splitlines():
            if line.strip().startswith("SETUP_COMPLETE="):
                return
        if existing and not existing.endswith("\n"):
            existing += "\n"
        CONFIG_FILE.write_text(existing + "SETUP_COMPLETE=true\n")
    else:
        CONFIG_FILE.write_text(ENV_TEMPLATE + "\nSETUP_COMPLETE=true\n")
    try:
        CONFIG_FILE.chmod(0o600)
    except OSError:
        pass


def _brew_pkg(missing: list[str]) -> list[str]:
    pkgs: list[str] = []
    for bin_name in missing:
        if bin_name in ("ffmpeg", "ffprobe"):
            if "ffmpeg" not in pkgs:
                pkgs.append("ffmpeg")
        elif bin_name == "yt-dlp":
            if "yt-dlp" not in pkgs:
                pkgs.append("yt-dlp")
        else:
            pkgs.append(bin_name)
    return pkgs


def _install_macos(missing: list[str]) -> tuple[bool, str]:
    if _which("brew") is None:
        return False, (
            "Homebrew is not installed. Install it from https://brew.sh, then re-run setup. "
            "Or install manually: `brew install " + " ".join(_brew_pkg(missing)) + "`"
        )
    pkgs = _brew_pkg(missing)
    if not pkgs:
        return True, "nothing to install"
    cmd = ["brew", "install", *pkgs]
    print(f"[zta-watch setup] running: {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        return False, f"brew install failed with exit code {result.returncode}"
    return True, f"installed via brew: {', '.join(pkgs)}"


def _install_hint_linux(missing: list[str]) -> str:
    pkgs = _brew_pkg(missing)
    hints = []
    if "ffmpeg" in pkgs:
        hints.append("apt: `sudo apt install ffmpeg` or dnf: `sudo dnf install ffmpeg`")
    if "yt-dlp" in pkgs:
        hints.append("`pipx install yt-dlp` (recommended) or `pip install --user yt-dlp`")
    return "\n  ".join(hints) if hints else "nothing to install"


def _install_hint_windows(missing: list[str]) -> str:
    pkgs = _brew_pkg(missing)
    hints = []
    if "ffmpeg" in pkgs:
        hints.append("winget: `winget install Gyan.FFmpeg`")
    if "yt-dlp" in pkgs:
        hints.append("winget: `winget install yt-dlp.yt-dlp` or pip: `pip install --user yt-dlp`")
    return "\n  ".join(hints) if hints else "nothing to install"


def _status() -> dict:
    missing = _check_binaries()
    has_key, backend = _have_api_key()
    ytdlp_stale, ytdlp_version = _check_ytdlp_stale()

    if not missing and has_key:
        status = "ready"
    elif missing and not has_key:
        status = "needs_install_and_key"
    elif missing:
        status = "needs_install"
    else:
        status = "needs_key"

    return {
        "status": status,
        "first_run": is_first_run(),
        "missing_binaries": missing,
        "ytdlp_stale": ytdlp_stale,
        "ytdlp_version": ytdlp_version,
        "whisper_backend": backend,
        "has_api_key": has_key,
        "config_file": str(CONFIG_FILE),
        "platform": platform.system(),
    }


def cmd_check() -> int:
    s = _status()
    if s["status"] == "ready":
        # Stale yt-dlp is a soft warning, not a hard fail — emit and exit 0.
        if s["ytdlp_stale"]:
            sys.stderr.write(
                f"[zta-watch] WARNING: yt-dlp is stale ({s['ytdlp_version']}). "
                "YouTube may 403 downloads. Run: brew upgrade yt-dlp\n"
            )
            sys.stderr.flush()
        return 0

    parts = []
    if s["missing_binaries"]:
        parts.append(f"missing binaries: {', '.join(s['missing_binaries'])}")
    if not s["has_api_key"]:
        parts.append("no Whisper API key (GROQ_API_KEY or OPENAI_API_KEY)")
    installer = Path(__file__).resolve()
    sys.stderr.write(
        f"[zta-watch] setup incomplete ({'; '.join(parts)}). "
        f"Run: python3 {installer}\n"
    )
    sys.stderr.flush()

    if s["missing_binaries"] and not s["has_api_key"]:
        return 4
    if s["missing_binaries"]:
        return 2
    return 3


def cmd_json() -> int:
    json.dump(_status(), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def cmd_install() -> int:
    missing = _check_binaries()
    installed_deps = False
    if missing:
        system = platform.system()
        if system == "Darwin":
            ok, msg = _install_macos(missing)
            print(f"[zta-watch setup] {msg}", file=sys.stderr)
            if not ok:
                return 2
            still_missing = _check_binaries()
            if still_missing:
                print(f"[zta-watch setup] still missing after install: {', '.join(still_missing)}", file=sys.stderr)
                return 2
            installed_deps = True
        elif system == "Linux":
            print("[zta-watch setup] dependencies missing on Linux — please install:", file=sys.stderr)
            print("  " + _install_hint_linux(missing), file=sys.stderr)
            return 2
        elif system == "Windows":
            print("[zta-watch setup] dependencies missing on Windows — please install:", file=sys.stderr)
            print("  " + _install_hint_windows(missing), file=sys.stderr)
            return 2
        else:
            print(f"[zta-watch setup] unsupported platform ({system}) for auto-install. Install manually:", file=sys.stderr)
            print(f"  missing: {', '.join(missing)}", file=sys.stderr)
            return 2

    created = _scaffold_env()
    if created:
        print(f"[zta-watch setup] created config: {CONFIG_FILE}")
    else:
        print(f"[zta-watch setup] config exists: {CONFIG_FILE}")

    # Even if all binaries are present, yt-dlp ages quickly. Auto-upgrade on
    # macOS so members don't 403 on their first /zta-watch run.
    ytdlp_stale, ytdlp_version = _check_ytdlp_stale()
    if ytdlp_stale and platform.system() == "Darwin" and _which("brew") is not None:
        print(f"[zta-watch setup] yt-dlp is stale ({ytdlp_version}); upgrading via brew…", file=sys.stderr)
        upgrade_result = subprocess.run(["brew", "upgrade", "yt-dlp"])
        if upgrade_result.returncode == 0:
            _, new_version = _check_ytdlp_stale()
            print(f"[zta-watch setup] yt-dlp now at {new_version}", file=sys.stderr)
        else:
            print(
                f"[zta-watch setup] brew upgrade yt-dlp failed (exit {upgrade_result.returncode}). "
                "Run manually before first /zta-watch use.",
                file=sys.stderr,
            )
    elif ytdlp_stale:
        print(
            f"[zta-watch setup] WARNING: yt-dlp is stale ({ytdlp_version}). "
            "Upgrade before first use or YouTube downloads will 403.",
            file=sys.stderr,
        )

    has_key, backend = _have_api_key()
    if has_key:
        _write_setup_complete()
        print(f"[zta-watch setup] ready. whisper backend: {backend}")
        if installed_deps:
            print("[zta-watch setup] installed dependencies; /zta-watch is fully set up.")
        return 0

    print("")
    print("[zta-watch setup] one step left: add a Whisper API key.")
    print("")
    print(f"  Edit {CONFIG_FILE} and set either:")
    print("    GROQ_API_KEY=...    (preferred — cheap, fast, generous free tier; console.groq.com/keys)")
    print("    OPENAI_API_KEY=...  (fallback; platform.openai.com/api-keys)")
    print("")
    print("  Without a key, /zta-watch still works but videos without captions come back frames-only.")
    return 3


def main() -> int:
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--check":
            return cmd_check()
        if arg == "--json":
            return cmd_json()
    return cmd_install()


if __name__ == "__main__":
    raise SystemExit(main())
