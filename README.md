# Quarterly Theory Discord Bot

Posts a card to a Discord webhook whenever a quarter starts or ends on the yearly,
monthly, weekly, daily (sessions) and micro (90 min) cycles. When several cycles
shift at the same moment they arrive together as one message.

Boundaries follow the chart in UTC. Everything shown in Discord is Pakistan time (PKT, UTC+5).

---

## Fully automated on GitHub (no server, no PC left on)

A GitHub Actions workflow runs every 5 minutes, posts any phase shift since its last run,
and remembers its place on a branch called `state` so nothing is ever sent twice.

1. **Create the webhook** in Discord: Channel > Edit Channel > Integrations > Webhooks > New Webhook > Copy Webhook URL.
2. **Create a public GitHub repo** and upload every file in this folder, including the
   `.github/workflows/` folder (the hidden folder must be uploaded, or use `git push`).
3. **Add the webhook as a secret** (never put it in a file; the repo is public):
   Repo > Settings > Secrets and variables > Actions > **Secrets** > New repository secret
   Name: `DISCORD_WEBHOOK_URL` · Value: your webhook URL.
4. **Allow the workflow to save state**:
   Repo > Settings > Actions > General > Workflow permissions > **Read and write permissions** > Save.
5. **Start it**: Repo > Actions > "Quarterly Theory alerts" > **Run workflow**.
   The first run posts the live board and creates the `state` branch. After that it is hands-off.

Optional settings go in Settings > Secrets and variables > Actions > **Variables**
(not Secrets): `MENTION_ROLE_ID`, `BOT_AVATAR_URL`, `BOT_NAME`, `TIMEFRAMES`
(any of `yearly,monthly,weekly,daily,micro`), `SHOW_UTC`, `SNAPSHOT_ON_START`.

### Things to know about GitHub Actions
- **Alerts can be a few minutes late.** GitHub's scheduler is best-effort and can start runs 5-30 minutes
  after the scheduled time at busy periods. The card always shows the true shift time.
- **Nothing is lost if a run is skipped.** The next run delivers any missed shift once. After a long
  outage (more than 6 missed shifts) you get one "catch-up" card with the current phases.
- **Inactivity:** GitHub pauses scheduled workflows in a public repo after 60 days without repo
  activity. The bot commits to the `state` branch about every 90 minutes, which should count, but if
  alerts ever stop, open the Actions tab and press "Enable workflow".
- **Public repo:** only the code is public. The webhook URL stays hidden in Secrets. Never commit a `.env`.
- Actions minutes are free for public repos.

---

## Run it locally instead
```
pip install -r requirements.txt
copy .env.example .env      # Windows   (cp on Linux/Mac), then put your webhook URL in .env
python quarterly_bot.py
```

| Command | What it does |
|---|---|
| `python quarterly_bot.py` | Run forever on your own machine and post at every shift |
| `python quarterly_bot.py --tick` | One pass: post anything new since the last run (what the workflow uses) |
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
