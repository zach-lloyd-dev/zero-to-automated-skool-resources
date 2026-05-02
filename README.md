# Zero to Automated - Skool Resources

Companion resources for the **Claude Code 101** course in the Zero to Automated Skool community.

## What's Inside

### Skills (Lesson 11)
8 ready-to-use Claude Code skills you can install with one command:

| Skill | What It Does |
|-------|-------------|
| `/summarize` | Summarize any document into key points, action items, and TLDR |
| `/meeting-notes` | Extract decisions, action items, and follow-ups from meeting transcripts |
| `/research` | Research any topic with structured analysis and recommendations |
| `/weekly-report` | Generate weekly business reports from notes and project data |
| `/business-case` | Build ROI analysis with costs, projections, and risk assessment |
| `/self-interview` | Guided questions to clarify your thinking on any decision |
| `/lead-magnet` | Create lead magnet concepts tailored to your offer |
| `/onboarding-doc` | Build onboarding docs for contractors and team members |

### Hooks (Lesson 12)
4 hook configurations for automating Claude Code:

| Hook | Event | What It Does |
|------|-------|-------------|
| Context Loader | SessionStart | Auto-loads your project context every session |
| Safety Guardrail | PreToolUse | Blocks dangerous commands before they execute |
| Quality Check | Stop | AI reviews every response for completeness |
| Notification | Stop | Desktop notification when Claude finishes |

### PDF Resources
Printable reference materials:
- **Plan Mode Decision Tree** (Lesson 10) - When to use Plan Mode
- **Project Workflow Checklist** (Lesson 13) - The 5-step project workflow

## Quick Install

### Skills (one command)

```bash
git clone https://github.com/zach-lloyd-dev/zero-to-automated-skool-resources.git
cd zero-to-automated-skool-resources
bash install.sh
```

This copies all 8 skills to `~/.claude/skills/`. Existing skills with the same name are not overwritten.

### Hooks (manual)

Hooks need to be added to your Claude Code settings. The easiest way:

1. Open Claude Code
2. Type `/hooks`
3. Follow the interactive menu

Or copy the configs from the `hooks/` folder into your settings file.

## Updating

Pull the latest resources anytime:

```bash
cd zero-to-automated-skool-resources
git pull
bash install.sh
```

## Course

These resources are companions to the [Zero to Automated](https://www.skool.com/zero-to-automated) Claude Code 101 course. Each resource corresponds to a specific lesson.

## Support

Questions? Post in the Skool community. We're here to help.
