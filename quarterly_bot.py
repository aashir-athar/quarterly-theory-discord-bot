#!/usr/bin/env python3
"""
Quarterly Theory -> Discord webhook bot
=======================================

Posts a "phase shift" card to a Discord webhook every time a quarter starts or
ends on any of the five cycles:

    yearly · monthly · weekly · daily (sessions) · micro (90-minute)

Quarter boundaries are computed in UTC (as in the Quarterly Theory chart).
Everything the reader sees is shown in Pakistan time (PKT, UTC+5).

    A = Accumulation   M = Manipulation   D = Distribution   X = Continue / Reversal

Usage
-----
    python quarterly_bot.py                  run forever, post to the webhook
    python quarterly_bot.py --snapshot       post the live board once and exit
    python quarterly_bot.py --next 12        list the next 12 phase shifts
    python quarterly_bot.py --at "2026-11-09 05:00"   preview the shift at a PKT time
    add --dry-run to any command to print the payload instead of posting
"""
from __future__ import annotations

import argparse
import calendar
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

try:
    from zoneinfo import ZoneInfo

    PKT = ZoneInfo("Asia/Karachi")
except Exception:  # tzdata missing (common on Windows) - Pakistan has no DST
    PKT = timezone(timedelta(hours=5), "PKT")

UTC = timezone.utc
log = logging.getLogger("quarterly-bot")

# --------------------------------------------------------------------------- #
#  Design tokens - one colour + one glyph per phase, used everywhere
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Phase:
    letter: str
    name: str
    color: int
    dot: str
    brief: str


PHASES = (
    Phase("A", "Accumulation", 0x3B82F6, "🔵", "Range is building. Mark the highs and lows. Don't chase."),
    Phase("M", "Manipulation", 0xF59E0B, "🟠", "Liquidity grab. Expect the fake move. Wait for the sweep to fail."),
    Phase("D", "Distribution", 0xEF4444, "🔴", "The real move. Trade with it once manipulation is done."),
    Phase("X", "Continue / Reversal", 0x10B981, "🟢", "Continue or reverse. Manage the trade, watch for exhaustion."),
)
IDLE_COLOR = 0x64748B

SESSIONS = ("Asia", "London", "New York AM", "New York PM")
DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday")

TF_ORDER = ("yearly", "monthly", "weekly", "daily", "micro")
TF_META = {
    "yearly": ("🗓️", "YEARLY"),
    "monthly": ("📆", "MONTHLY"),
    "weekly": ("📅", "WEEKLY"),
    "daily": ("☀️", "DAILY · SESSIONS"),
    "micro": ("⏱️", "MICRO · 90 MIN"),
}
TF_TITLE = {"yearly": "Yearly", "monthly": "Monthly", "weekly": "Weekly", "daily": "Daily", "micro": "Micro"}

# --------------------------------------------------------------------------- #
#  Quarter engine (all maths in UTC, exactly as drawn in the chart)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Window:
    tf: str
    q: Optional[int]  # 0..3 -> Q1..Q4, None = outside the cycle (weekend break)
    start: datetime  # UTC, inclusive
    end: datetime  # UTC, exclusive
    context: str = ""

    @property
    def key(self) -> tuple:
        return (self.tf, self.q, self.start)

    @property
    def phase(self) -> Optional[Phase]:
        return None if self.q is None else PHASES[self.q]


def _add_months(year: int, month: int, n: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) + n
    return idx // 12, idx % 12 + 1


def _midnight(t: datetime) -> datetime:
    return t.replace(hour=0, minute=0, second=0, microsecond=0)


def yearly(t: datetime) -> Window:
    q = (t.month - 1) // 3
    first = q * 3 + 1
    start = datetime(t.year, first, 1, tzinfo=UTC)
    ny, nm = _add_months(t.year, first, 3)
    end = datetime(ny, nm, 1, tzinfo=UTC)
    ctx = f"{calendar.month_abbr[first]} – {calendar.month_abbr[first + 2]} {t.year}"
    return Window("yearly", q, start, end, ctx)


def monthly(t: datetime) -> Window:
    # Week 1 = days 1-7, Week 2 = 8-14, Week 3 = 15-21, Week 4 = 22 -> month end
    wk = min((t.day - 1) // 7, 3)
    start = datetime(t.year, t.month, wk * 7 + 1, tzinfo=UTC)
    if wk < 3:
        end = start + timedelta(days=7)
    else:
        ny, nm = _add_months(t.year, t.month, 1)
        end = datetime(ny, nm, 1, tzinfo=UTC)
    return Window("monthly", wk, start, end, f"Week {wk + 1} · {calendar.month_abbr[t.month]}")


def weekly(t: datetime) -> Window:
    day0 = _midnight(t)
    wd = t.weekday()  # Mon=0
    if wd <= 3:  # Q1 Mon · Q2 Tue · Q3 Wed · Q4 Thu
        return Window("weekly", wd, day0, day0 + timedelta(days=1), DAY_NAMES[wd])
    friday = day0 - timedelta(days=wd - 4)
    next_monday = day0 + timedelta(days=7 - wd)
    return Window("weekly", None, friday, next_monday, "Weekend break")


def daily(t: datetime) -> Window:
    q = t.hour // 6  # Asia · London · New York AM · New York PM
    start = _midnight(t) + timedelta(hours=6 * q)
    return Window("daily", q, start, start + timedelta(hours=6), SESSIONS[q])


def micro(t: datetime) -> Window:
    slot = (t.hour * 60 + t.minute) // 90  # 16 slots a day, 4 per session
    start = _midnight(t) + timedelta(minutes=90 * slot)
    return Window("micro", slot % 4, start, start + timedelta(minutes=90), SESSIONS[slot // 4])


ENGINE = {"yearly": yearly, "monthly": monthly, "weekly": weekly, "daily": daily, "micro": micro}


def snapshot(t: datetime) -> dict[str, Window]:
    return {tf: ENGINE[tf](t) for tf in TF_ORDER}


# --------------------------------------------------------------------------- #
#  Presentation helpers (everything the reader sees is PKT)
# --------------------------------------------------------------------------- #


def pkt(dt: datetime) -> datetime:
    return dt.astimezone(PKT)


def fmt(dt: datetime) -> str:
    d = pkt(dt)
    return f"{d:%a %d %b} · {d:%I:%M %p}"


def rel(dt: datetime) -> str:
    return f"<t:{int(dt.timestamp())}:R>"


def qname(w: Window) -> str:
    return f"Q{w.q + 1} · {w.phase.name}"


def bar(q: int) -> str:
    return "▰" * (q + 1) + "▱" * (3 - q)


def rail(q: int) -> str:
    return " › ".join(f"[{p.letter}]" if i == q else f" {p.letter} " for i, p in enumerate(PHASES))


def next_up(w: Window) -> str:
    if w.q is None:
        return "Q1 · Accumulation"
    if w.q < 3:
        return f"Q{w.q + 2} · {PHASES[w.q + 1].name}"
    if w.tf == "weekly":
        return "Weekend break"
    return "Q1 · Accumulation (new cycle)"


def window_block(w: Window, show_utc: bool) -> str:
    lines = [f"FROM  {fmt(w.start)}", f"TO    {fmt(w.end)}"]
    if show_utc:
        lines.append(f"UTC   {w.start:%d %b %H:%M} → {w.end:%d %b %H:%M}")
    return "```\n" + "\n".join(lines) + "\n```"


FOOTER = {"text": "Quarterly Theory · all times PKT (UTC+5)"}


def transition_embed(prev: Window, new: Window, show_utc: bool) -> dict:
    icon, label = TF_META[new.tf]
    author = {"name": f"{icon}  {label}"}

    # Cycle finished and nothing follows (weekly Q4 -> weekend break)
    if new.q is None:
        return {
            "author": author,
            "title": "⚪ Weekly cycle complete",
            "description": f"✔ ~~{qname(prev)}~~ closed\n\n> Market week is done. Review, journal, reset.",
            "color": IDLE_COLOR,
            "fields": [
                {"name": "⏭ Resumes", "value": f"**{fmt(new.end)}**\n{rel(new.end)}", "inline": False},
            ],
            "footer": FOOTER,
        }

    ph = new.phase
    live = f"▶ **{qname(new)}** live"
    if new.q == 0 and prev is not None and prev.q is not None:
        live += " · 🔁 new cycle"
    if prev is not None and prev.q is not None:
        desc = f"✔ ~~{qname(prev)}~~ closed\n{live}"
    else:
        desc = f"{live} · 🔁 new cycle"
    desc += f"\n\n> {ph.brief}"

    return {
        "author": author,
        "title": f"{ph.dot} {TF_TITLE[new.tf]} Q{new.q + 1} · {ph.name} — {new.context}",
        "description": desc,
        "color": ph.color,
        "fields": [
            {"name": "🕒 Window · PKT", "value": window_block(new, show_utc), "inline": False},
            {"name": "⏳ Ends", "value": rel(new.end), "inline": True},
            {"name": "📊 Cycle", "value": f"`{bar(new.q)}` {new.q + 1}/4\n`{rail(new.q)}`", "inline": True},
            {"name": "⏭ Next", "value": next_up(new), "inline": True},
        ],
        "footer": FOOTER,
    }


def transition_payload(cfg: "Config", at: datetime, changes: list[tuple[Window, Window]]) -> dict:
    embeds = [transition_embed(p, n, cfg.show_utc) for p, n in changes]
    head = f"🔔 **Phase shift** · {fmt(at)} PKT"
    if cfg.role_id:
        head = f"<@&{cfg.role_id}> {head}"
    return _envelope(cfg, head, embeds)


def snapshot_payload(cfg: "Config", state: dict[str, Window]) -> dict:
    fields = []
    for tf in cfg.timeframes:
        w = state[tf]
        icon, label = TF_META[tf]
        if w.q is None:
            value = f"⚪ **{w.context}**\nResumes {rel(w.end)} · {fmt(w.end)}"
        else:
            value = f"{w.phase.dot} **{qname(w)}** — {w.context}\nEnds {rel(w.end)} · {fmt(w.end)}"
        fields.append({"name": f"{icon}  {label}", "value": value, "inline": False})
    lead = state["daily"] if state["daily"].q is not None else None
    embed = {
        "title": "📡 Quarterly Theory · Live board",
        "description": "Current phase on every timeframe. A card drops at each shift.",
        "color": lead.phase.color if lead else IDLE_COLOR,
        "fields": fields,
        "footer": FOOTER,
    }
    return _envelope(cfg, None, [embed])


def _envelope(cfg: "Config", content: Optional[str], embeds: list[dict]) -> dict:
    payload: dict = {
        "username": cfg.bot_name,
        "embeds": embeds,
        "allowed_mentions": {"roles": [cfg.role_id]} if cfg.role_id else {"parse": []},
    }
    if content:
        payload["content"] = content
    if cfg.avatar_url:
        payload["avatar_url"] = cfg.avatar_url
    return payload


# --------------------------------------------------------------------------- #
#  Config + webhook delivery
# --------------------------------------------------------------------------- #


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    webhook_url: str
    bot_name: str
    avatar_url: str
    role_id: str
    timeframes: tuple
    show_utc: bool
    snapshot_on_start: bool
    max_late: int
    dry_run: bool = False


def load_config(dry_run: bool) -> Config:
    load_dotenv()
    raw = os.getenv("TIMEFRAMES", ",".join(TF_ORDER))
    wanted = {x.strip().lower() for x in raw.split(",") if x.strip()}
    unknown = wanted - set(TF_ORDER)
    if unknown:
        sys.exit(f"Unknown TIMEFRAMES: {', '.join(sorted(unknown))}. Valid: {', '.join(TF_ORDER)}")
    return Config(
        webhook_url=os.getenv("DISCORD_WEBHOOK_URL", "").strip(),
        bot_name=os.getenv("BOT_NAME", "Quarterly Theory"),
        avatar_url=os.getenv("BOT_AVATAR_URL", "").strip(),
        role_id=os.getenv("MENTION_ROLE_ID", "").strip(),
        timeframes=tuple(tf for tf in TF_ORDER if tf in wanted),
        show_utc=_env_bool("SHOW_UTC", False),
        snapshot_on_start=_env_bool("SNAPSHOT_ON_START", True),
        max_late=int(os.getenv("MAX_LATE_SECONDS", "600")),
        dry_run=dry_run,
    )


def post(cfg: Config, payload: dict) -> bool:
    if cfg.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return True
    if not cfg.webhook_url:
        log.error("DISCORD_WEBHOOK_URL is empty. Set it in .env (or use --dry-run).")
        return False
    for attempt in range(5):
        try:
            r = requests.post(cfg.webhook_url, json=payload, timeout=15)
        except requests.RequestException as exc:
            log.warning("Network error (%s). Retrying...", exc)
            time.sleep(2 ** attempt)
            continue
        if r.status_code in (200, 204):
            return True
        if r.status_code == 429:
            try:
                wait = float(r.json().get("retry_after", 1))
            except Exception:
                wait = 1.0
            log.warning("Rate limited, waiting %.1fs", wait)
            time.sleep(wait + 0.25)
            continue
        if r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        log.error("Webhook rejected the message (%s): %s", r.status_code, r.text[:300])
        return False
    log.error("Gave up posting after 5 attempts.")
    return False


# --------------------------------------------------------------------------- #
#  Scheduler
# --------------------------------------------------------------------------- #


def utcnow() -> datetime:
    return datetime.now(UTC)


def sleep_until(target: datetime) -> None:
    # Short slices so a laptop sleeping / clock change can't make us oversleep.
    while True:
        remaining = (target - utcnow()).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 30))


def run(cfg: Config) -> None:
    state = snapshot(utcnow())
    log.info("Quarterly Theory bot online · timeframes: %s", ", ".join(cfg.timeframes))
    if cfg.snapshot_on_start:
        post(cfg, snapshot_payload(cfg, state))

    while True:
        target = min(state[tf].end for tf in cfg.timeframes)
        log.info("Next phase shift: %s PKT", fmt(target))
        sleep_until(target)

        now = utcnow()
        new = snapshot(now)
        changes = [(state[tf], new[tf]) for tf in cfg.timeframes if state[tf].key != new[tf].key]
        state = new
        if not changes:
            continue

        late = (now - target).total_seconds()
        if late > cfg.max_late:
            log.warning("Woke %.0fs late (system asleep?) - skipping stale alert and resyncing.", late)
            continue

        ok = post(cfg, transition_payload(cfg, target, changes))
        log.info("Sent %d card(s) for %s PKT - %s", len(changes), fmt(target), "ok" if ok else "FAILED")


def check_once(cfg: Config, state_file: Path) -> None:
    now = utcnow()
    if not state_file.exists():
        save_check_time(state_file, now)
        log.info("No prior check state; initialized at %s UTC.", now.isoformat())
        return

    try:
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        last_check = datetime.fromisoformat(saved["last_check"])
        if last_check.tzinfo is None:
            raise ValueError("last_check must include a timezone")
        last_check = last_check.astimezone(UTC)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f"Could not read check state from {state_file}: {exc}") from exc

    if last_check > now:
        raise RuntimeError(f"Check state in {state_file} is in the future.")
    if (now - last_check).total_seconds() > cfg.max_late:
        log.warning("Check state is stale; skipping old shifts and resyncing.")
        save_check_time(state_file, now)
        return

    cursor = last_check
    while True:
        before = snapshot(cursor)
        target = min(before[tf].end for tf in cfg.timeframes)
        if target > now:
            break

        after = snapshot(target)
        changes = [
            (before[tf], after[tf])
            for tf in cfg.timeframes
            if before[tf].key != after[tf].key
        ]
        if changes and not post(cfg, transition_payload(cfg, target, changes)):
            raise RuntimeError(f"Failed to post the phase shift at {target.isoformat()}.")
        cursor = target
        save_check_time(state_file, cursor)

    save_check_time(state_file, now)
    log.info("Checked phase shifts through %s UTC.", now.isoformat())


def save_check_time(state_file: Path, checked_at: datetime) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps({"last_check": checked_at.astimezone(UTC).isoformat()}),
        encoding="utf-8",
    )


def list_next(cfg: Config, n: int) -> None:
    t = utcnow()
    for _ in range(n):
        state = snapshot(t)
        target = min(state[tf].end for tf in cfg.timeframes)
        after = snapshot(target)
        parts = []
        for tf in cfg.timeframes:
            if state[tf].key != after[tf].key:
                w = after[tf]
                tag = "break" if w.q is None else f"Q{w.q + 1}"
                parts.append(f"{tf} {tag} ({w.context})")
        print(f"{fmt(target)} PKT  ->  " + " | ".join(parts))
        t = target


def preview_at(cfg: Config, when_pkt: str) -> None:
    try:
        local = datetime.strptime(when_pkt, "%Y-%m-%d %H:%M").replace(tzinfo=PKT)
    except ValueError:
        sys.exit('--at expects PKT time like "2026-11-09 05:00"')
    at = local.astimezone(UTC)
    before, after = snapshot(at - timedelta(seconds=1)), snapshot(at)
    changes = [(before[tf], after[tf]) for tf in cfg.timeframes if before[tf].key != after[tf].key]
    if not changes:
        print("No phase shift at that exact minute. Use --next 10 to see real boundaries.")
        return
    if not post(cfg, transition_payload(cfg, at, changes)):
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Quarterly Theory Discord webhook bot (PKT display)")
    ap.add_argument("--dry-run", action="store_true", help="print payloads instead of posting")
    ap.add_argument("--snapshot", action="store_true", help="post the live board once and exit")
    ap.add_argument("--check", action="store_true", help="check for phase shifts since the last run and exit")
    ap.add_argument(
        "--state-file",
        type=Path,
        default=Path(".quarterly-bot-state.json"),
        help="state file used by --check",
    )
    ap.add_argument("--next", type=int, metavar="N", help="list the next N phase shifts and exit")
    ap.add_argument("--at", metavar='"YYYY-MM-DD HH:MM"', help="preview the shift at a PKT time and exit")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    cfg = load_config(args.dry_run)

    if args.next:
        return list_next(cfg, args.next)
    if args.at:
        return preview_at(cfg, args.at)
    if args.check:
        try:
            check_once(cfg, args.state_file)
        except RuntimeError as exc:
            sys.exit(str(exc))
        return
    if args.snapshot:
        if not post(cfg, snapshot_payload(cfg, snapshot(utcnow()))):
            sys.exit(1)
        return
    if not cfg.webhook_url and not cfg.dry_run:
        sys.exit("Set DISCORD_WEBHOOK_URL in .env first (see .env.example).")
    try:
        run(cfg)
    except KeyboardInterrupt:
        log.info("Stopped.")


if __name__ == "__main__":
    main()
