# Quarterly Theory Discord Bot

[![Quarterly Theory alerts](https://github.com/aashir-athar/quarterly-theory-discord-bot/actions/workflows/quarterly.yml/badge.svg)](https://github.com/aashir-athar/quarterly-theory-discord-bot/actions/workflows/quarterly.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Discord webhook](https://img.shields.io/badge/Discord-webhook-5865F2.svg)](https://discord.com/developers/docs/resources/webhook)

A Python **Discord bot for Quarterly Theory phase alerts**. It tracks yearly,
monthly, weekly, daily-session, and 90-minute micro cycles, then posts a Discord
webhook notification when one or more phases change. The bot can run automatically
with GitHub Actions or continuously on your own machine.

> Phase labels and session times are configurable chart references, not financial
> advice or trading signals.

## Features

- Automated Discord webhook alerts for Quarterly Theory phase changes.
- Yearly, monthly, weekly, daily-session, and 90-minute micro timeframes.
- Combined notifications when multiple cycles change together.
- Discord embeds show phase, cycle window, next phase, and relative end time.
- Optional role mentions, custom bot name and avatar, and UTC timestamps.
- GitHub Actions can keep the bot running in five-hour sessions, hand off to the
  next session, and use an hourly watchdog to restart a broken chain.
- Delivery state is stored on a separate `state` branch to avoid reposting
  already processed shifts.
- Preview the live board, upcoming phase boundaries, or a specific transition.

## Run automatically with GitHub Actions

The public repository includes a self-restarting GitHub Actions workflow. Each run
keeps the bot online for five hours, then queues its successor. An hourly watchdog
restarts the chain if a run fails to hand off. GitHub-hosted runners are still
temporary, and GitHub does not guarantee uninterrupted service or exact start times.

### Setup

1. In Discord, create a webhook from **Channel Settings → Integrations → Webhooks**.
2. In your GitHub repository, open **Settings → Secrets and variables → Actions**.
   Add a repository secret named `DISCORD_WEBHOOK_URL` with the webhook URL as its
   value. Keep the URL in a secret; never commit it or put it in a workflow file.
3. Under **Settings → Actions → General → Workflow permissions**, allow read and
   write permissions so the workflow can save its deduplication state to the `state`
   branch.
4. Open **Actions → Quarterly Theory alerts** and select **Run workflow** once to
   start the bot chain. The first run posts the live board by default and initializes
   state. You can stop the chain by cancelling the active run; the watchdog may
   restart it if the workflow remains enabled.

Optional settings can be added under **Settings → Secrets and variables → Actions
→ Variables**:

| Variable | Purpose | Default |
|---|---|---|
| `BOT_NAME` | Name displayed on Discord messages | `Quarterly Theory` |
| `BOT_AVATAR_URL` | Optional avatar image URL | Empty |
| `MENTION_ROLE_ID` | Discord role ID mentioned on phase changes | Empty |
| `TIMEFRAMES` | Comma-separated cycles: `yearly,monthly,weekly,daily,micro` | All cycles |
| `SHOW_UTC` | Include UTC boundaries alongside PKT times | `false` |
| `SNAPSHOT_ON_START` | Post the live board on the first run | `true` |

### Scheduling and delivery notes

- Each serving job is capped at 345 minutes by GitHub Actions and runs the bot for
  five hours before queuing the next session.
- The watchdog checks hourly. GitHub may delay or skip scheduled jobs, so this is
  best-effort automation, not guaranteed 24/7 infrastructure.
- The bot saves delivery state on the `state` branch and catches up on missed phase
  changes after restarts. To start fresh instead of replaying old state, delete that
  branch before the first run; the bot will initialize a new live snapshot.
- GitHub can disable scheduled workflows in inactive repositories. If alerts stop,
  check the Actions tab and re-enable the workflow if needed.
- Only source code and workflow configuration are public. Keep `.env` and webhook
  credentials private.

## Run locally

Requires Python 3.12 or later and pip.

```shell
git clone https://github.com/aashir-athar/quarterly-theory-discord-bot.git
cd quarterly-theory-discord-bot
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`, add your Discord webhook URL, then start the bot:

```shell
# Windows PowerShell
Copy-Item .env.example .env

# macOS or Linux
cp .env.example .env

python quarterly_bot.py
```

The local `.env` file is ignored by Git. Never commit a real webhook URL.

## Commands

| Command | Description |
|---|---|
| `python quarterly_bot.py` | Run continuously and post alerts |
| `python quarterly_bot.py --tick` | Check once for new phase changes using saved state |
| `python quarterly_bot.py --serve 300 --state state.json` | Run the scheduler for 300 minutes, then exit |
| `python quarterly_bot.py --snapshot` | Post the current live board |
| `python quarterly_bot.py --next 12` | List the next 12 phase boundaries in PKT |
| `python quarterly_bot.py --at "2026-11-09 05:00"` | Preview/post a transition at a PKT time |
| Add `--dry-run` | Print the Discord payload instead of sending it |

## Quarterly Theory cycles

All cycle boundaries are calculated in UTC. Displayed times are Pakistan Standard
Time (PKT, UTC+5).

| Cycle | Phase mapping |
|---|---|
| Yearly | Q1 Jan–Mar, Q2 Apr–Jun, Q3 Jul–Sep, Q4 Oct–Dec |
| Monthly | Week 1: days 1–7; Week 2: 8–14; Week 3: 15–21; Week 4: 22–month end |
| Weekly | Monday–Thursday map to Q1–Q4; Friday through Sunday is the weekend break |
| Daily | 00–06 Asia, 06–12 London, 12–18 New York AM, 18–24 New York PM |
| Micro | Sixteen 90-minute slots per day, grouped into four slots per session |

The daily sessions begin in PKT at 05:00 (Asia), 11:00 (London), 17:00 (New York AM),
and 23:00 (New York PM).

## Configuration and security

Start from [`.env.example`](./.env.example) for local environment settings.
For GitHub Actions, add `DISCORD_WEBHOOK_URL` as a repository secret and optional
settings as Actions variables. The `.gitignore` excludes `.env` and local state files.

If a webhook URL is accidentally exposed, delete or regenerate it in Discord and
replace the `DISCORD_WEBHOOK_URL` GitHub secret immediately.

## Project files

```text
.
├── .github/workflows/quarterly.yml  # Scheduled GitHub Actions workflow
├── .github/workflows/watchdog.yml   # Restarts the workflow chain if needed
├── scripts/save_state.sh            # Persists state to the state branch
├── .env.example                     # Local configuration template
├── .gitignore                       # Excludes secrets and generated state
├── quarterly_bot.py                 # Cycle calculations and Discord delivery
├── requirements.txt                 # Python dependencies
└── README.md
```
