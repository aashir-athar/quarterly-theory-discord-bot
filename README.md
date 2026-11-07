# Quarterly Theory Discord Bot

Posts a card to a Discord webhook whenever a quarter starts or ends on the yearly,
monthly, weekly, daily (sessions) and micro (90 min) cycles. When several cycles
shift at the same moment they arrive together as one message.

Boundaries follow the chart in UTC. Everything shown in Discord is Pakistan time (PKT, UTC+5).

## Setup
```
pip install -r requirements.txt
copy .env.example .env      # Windows   (cp on Linux/Mac)
# put your webhook URL in .env
python quarterly_bot.py
```

## Commands
| Command | What it does |
|---|---|
| `python quarterly_bot.py` | Run forever and post at every shift |
| `python quarterly_bot.py --snapshot` | Post the live board (current phase of every cycle) |
| `python quarterly_bot.py --next 12` | List the next 12 shifts in PKT |
| `python quarterly_bot.py --at "2026-11-09 05:00"` | Post the card for the shift at that PKT time |
| add `--dry-run` | Print the JSON instead of posting |

## How cycles are mapped (UTC)
- Yearly: Q1 Jan-Mar, Q2 Apr-Jun, Q3 Jul-Sep, Q4 Oct-Dec
- Monthly: Week 1 = days 1-7, Week 2 = 8-14, Week 3 = 15-21, Week 4 = 22-month end
- Weekly: Mon / Tue / Wed / Thu = Q1-Q4. Friday to Monday is shown as a weekend break
- Daily: 00-06 Asia, 06-12 London, 12-18 New York AM, 18-24 New York PM
- Micro: 16 slots of 90 minutes a day, four per session, exactly as in the chart

In PKT the day starts at 05:00, so Asia = 05:00, London = 11:00, New York AM = 17:00, New York PM = 23:00.

## Keep it running
It must be running to send alerts. Use a VPS, or on Windows Task Scheduler "At startup",
or `pm2 start quarterly_bot.py --interpreter python`.

## Run automatically with GitHub Actions

The included workflow checks for phase shifts every five hours (at 00:00, 05:00, 10:00,
15:00, and 20:00 UTC) and can post a live snapshot when started manually. GitHub-hosted runners are short-lived, so the workflow
uses a small Actions cache to remember its last check rather than keeping a process open.
GitHub scheduled workflows are best-effort and can be delayed; alerts are skipped if
the workflow has been inactive longer than `MAX_LATE_SECONDS`.

1. Add `DISCORD_WEBHOOK_URL` under the repository's **Settings → Secrets and variables
   → Actions → New repository secret**. Never commit `.env` or paste a webhook URL into
   workflow files.
2. Optionally add repository Actions variables such as `BOT_NAME`, `BOT_AVATAR_URL`,
   `MENTION_ROLE_ID`, `TIMEFRAMES`, and `SHOW_UTC`.
3. Keep the workflow enabled in the repository's **Actions** tab. Use
   **Quarterly Theory Discord Bot → Run workflow** to post a snapshot on demand.

The workflow catches up on phase shifts since its previous run for up to six hours
(`MAX_LATE_SECONDS=21600` by default). This is a periodic job, not a continuously running
process, and GitHub does not guarantee exact schedule timing.
