#!/bin/bash

# Zero to Automated - Claude Code 101 Toolkit Installer
# Installs skills and hooks from the course companion resources

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$HOME/.claude/skills"
SETTINGS_FILE="$HOME/.claude/settings.json"

echo ""
echo "======================================"
echo "  Zero to Automated - Toolkit Install"
echo "  Claude Code 101 Companion Resources"
echo "======================================"
echo ""

# --- SKILLS INSTALLATION ---

echo "STEP 1: Installing Skills"
echo "-------------------------"

# Create skills directory if it doesn't exist
mkdir -p "$SKILLS_DIR"

SKILLS=(summarize meeting-notes research weekly-report business-case self-interview lead-magnet onboarding-doc zta-watch)
INSTALLED=0
SKIPPED=0

for skill in "${SKILLS[@]}"; do
    if [ -d "$SKILLS_DIR/$skill" ]; then
        echo "  [skip] /$skill already exists"
        SKIPPED=$((SKIPPED + 1))
    else
        mkdir -p "$SKILLS_DIR/$skill"
        # Skills with bundled scripts/commands/etc. need a recursive copy.
        # Simple prompt-only skills only have SKILL.md. Detect by directory
        # contents so we don't have to special-case each skill.
        if [ -d "$SCRIPT_DIR/skills/$skill/scripts" ] || [ -d "$SCRIPT_DIR/skills/$skill/commands" ]; then
            cp -R "$SCRIPT_DIR/skills/$skill/." "$SKILLS_DIR/$skill/"
        else
            cp "$SCRIPT_DIR/skills/$skill/SKILL.md" "$SKILLS_DIR/$skill/SKILL.md"
        fi
        echo "  [ok]   /$skill installed"
        INSTALLED=$((INSTALLED + 1))
    fi
done

# zta-watch needs ffmpeg + yt-dlp. Run its preflight to surface any missing deps
# now rather than waiting until the user invokes the skill the first time.
if [ -f "$SKILLS_DIR/zta-watch/scripts/setup.py" ]; then
    echo ""
    echo "  Running /zta-watch preflight (checks for ffmpeg, yt-dlp, Whisper key)…"
    if python3 "$SKILLS_DIR/zta-watch/scripts/setup.py" --check 2>&1 | sed 's/^/    /'; then
        echo "  [ok]   /zta-watch ready"
    else
        echo "  [info] /zta-watch needs setup. Run: python3 $SKILLS_DIR/zta-watch/scripts/setup.py"
    fi
fi

echo ""
echo "  Skills: $INSTALLED installed, $SKIPPED skipped (already exist)"
echo ""

# --- HOOKS INSTALLATION ---

echo "STEP 2: Hooks Configuration"
echo "---------------------------"
echo ""
echo "  Hooks need to be added to your Claude Code settings."
echo "  You have two options:"
echo ""
echo "  Option A: Use the /hooks menu inside Claude Code (recommended)"
echo "            Just type /hooks and follow the prompts."
echo ""
echo "  Option B: Copy the combined config from:"
echo "            $SCRIPT_DIR/hooks/all-hooks-combined.json"
echo "            into your settings at: $SETTINGS_FILE"
echo ""

if [ -f "$SETTINGS_FILE" ]; then
    echo "  Your current settings file exists at:"
    echo "  $SETTINGS_FILE"
    echo ""
    echo "  To avoid overwriting your existing settings,"
    echo "  we recommend using /hooks or manually merging."
else
    echo "  No settings file found. You can copy the combined config:"
    echo "  cp $SCRIPT_DIR/hooks/all-hooks-combined.json $SETTINGS_FILE"
    echo ""
    read -p "  Copy all hooks to settings now? (y/N): " INSTALL_HOOKS
    if [ "$INSTALL_HOOKS" = "y" ] || [ "$INSTALL_HOOKS" = "Y" ]; then
        mkdir -p "$(dirname "$SETTINGS_FILE")"
        cp "$SCRIPT_DIR/hooks/all-hooks-combined.json" "$SETTINGS_FILE"
        echo "  [ok] Hooks installed to $SETTINGS_FILE"
    else
        echo "  [skip] Hooks not installed. Use /hooks in Claude Code to set up manually."
    fi
fi

echo ""
echo "======================================"
echo "  Installation Complete!"
echo "======================================"
echo ""
echo "  Your new skills:"
echo "    /summarize       - Summarize any document"
echo "    /meeting-notes   - Extract meeting notes from transcripts"
echo "    /research        - Research any topic"
echo "    /weekly-report   - Generate weekly business reports"
echo "    /business-case   - Build ROI analysis for decisions"
echo "    /self-interview  - Clarify your thinking with guided questions"
echo "    /lead-magnet     - Create lead magnet concepts"
echo "    /onboarding-doc  - Build contractor onboarding docs"
echo "    /zta-watch       - Watch any video (needs ffmpeg + yt-dlp + Whisper key)"
echo ""
echo "  To test: open Claude Code and type /summarize"
echo ""
echo "  Hook configs are in the hooks/ folder."
echo "  Use /hooks inside Claude Code to set them up."
echo ""
echo "  PDF resources are in the pdf-resources/ folder."
echo ""
