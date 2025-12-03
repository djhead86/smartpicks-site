#!/usr/bin/env python3
"""
SmartPicks v0.1.7-clean

Goal:
- Simple, disciplined betting analytics engine.
- Safe bankroll growth from $200 → $2000.
- No scope creep, minimal architecture, single-file script.
"""

import csv
import json
import os
import subprocess
from datetime import datetime, timezone
import requests

# ============================================================
# SECTION 1: CONFIG / CONSTANTS
# ============================================================

CONFIG_FILE = "config.json"
HISTORY_FILE = "bet_history.csv"
DATA_FILE = "data.json"
CLEANUP_FLAG = "cleanup_done.flag"

SPORTS = {
    "basketball_nba": "NBA",
    "americanfootball_nfl": "NFL",
    "icehockey_nhl": "NHL",
}

MARKETS = ["h2h", "spreads", "totals"]

MAX_ODDS = 200           # Ignore absurd lines beyond this
MAX_OPEN_BETS = 10       # Hard cap on simultaneous open bets

INJURY_HEAVY_PENALTY = 0.30
INJURY_LIGHT_PENALTY = 0.15


# ============================================================
# SECTION 2: BASIC HELPERS
# ============================================================

def load_config():
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def ensure_history_file():
    """Ensure bet_history.csv exists with the correct header."""
    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "sport", "event", "market", "team",
                "line", "odds", "bet_amount", "status", "result", "pnl"
            ])


def read_history():
    """Read all rows from bet_history.csv into a list of dicts."""
    ensure_history_file()
    rows = []
    with open(HISTORY_FILE, "r") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


def write_history(rows):
    """Rewrite bet_history.csv with the given rows."""
    if not rows:
        # If no rows, still ensure header exists
        ensure_history_file()
        return
    with open(HISTORY_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def normalize_str(s):
    """Lowercase, strip whitespace, collapse internal spaces."""
    if s is None:
        return ""
    return " ".join(str(s).strip().lower().split())


def safe_float(x, default=0.0):
    """Convert to float safely; fall back to default on error."""
    try:
        return float(x)
    except Exception:
        return default


# ============================================================
# SECTION 3: ONE-TIME HISTORY CLEANUP
# ============================================================

def cleanup_history_once():
    """
    Run exactly once to remove duplicate bets from old runs.

    Duplicates are defined as rows sharing the same
    (sport, event, market, team) after normalization.
    We keep the first occurrence (oldest) and drop later ones.
    This is purely to clean up messy history from early versions.
    """
    if os.path.exists(CLEANUP_FLAG):
        return

    if not os.path.exists(HISTORY_FILE):
        # Nothing to clean, but mark cleanup as done
        with open(CLEANUP_FLAG, "w") as f:
            f.write("no history to clean\n")
        return

    rows = read_history()
    if not rows:
        with open(CLEANUP_FLAG, "w") as f:
            f.write("empty history\n")
        return

    seen = set()
    cleaned = []

    for r in rows:
        key = (
            normalize_str(r.get("sport")),
            normalize_str(r.get("event")),
            normalize_str(r.get("market")),
            normalize_str(r.get("team")),
        )
        if key in seen:
            # Drop duplicate from older buggy runs
            continue
        seen.add(key)
        cleaned.append(r)

    write_history(cleaned)

    with open(CLEANUP_FLAG, "w") as f:
        f.write(f"cleanup completed at {datetime.now(timezone.utc)}\n")


# ============================================================
# SECTION 4: GRADING PREVIOUS BETS
# ============================================================

def fetch_scores(api_key, sport, days=3):
    """Fetch recent scores for a given sport from The Odds API."""
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/scores"
    params = {"apiKey": api_key, "daysFrom": days}
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return []
        return resp.json()
    except Exception:
        return []


def index_scores(scores):
    """Index scores by 'away @ home' event string."""
    idx = {}
    for g in scores:
        away = g.get("away_team")
        home = g.get("home_team")
        if away and home:
            idx[f"{away} @ {home}"] = g
    return idx


def parse_score(game, team):
    """Get the final score for a given team from a score object."""
    scores = game.get("scores", [])
    for s in scores:
        if s.get("name") == team:
            try:
                return int(s.get("score"))
            except Exception:
                return 0
    return 0


def grade_open_bets(api_key, history):
    """
    Update open bets with results where games are completed.
    Does not return bankroll; we compute bankroll from total PnL later.
    """
    if not history:
        return history

    open_by_sport = {}

    for r in history:
        if r.get("status") == "open":
            s = r["sport"]
            open_by_sport.setdefault(s, []).append(r)

    for sport, rows in open_by_sport.items():
        scores = fetch_scores(api_key, sport)
        idx = index_scores(scores)

        for row in rows:
            event = row["event"]
            game = idx.get(event)
            if not game or not game.get("completed", False):
                continue

            away = game["away_team"]
            home = game["home_team"]

            away_score = parse_score(game, away)
            home_score = parse_score(game, home)

            market = row["market"]
            team = row["team"]
            odds = safe_float(row["odds"])
            stake = safe_float(row["bet_amount"])

            result = None
            pnl = 0.0

            if market == "h2h":
                winner = away if away_score > home_score else home
                if team == winner:
                    result = "won"
                    pnl = stake * (abs(odds) / 100)
                else:
                    result = "lost"
                    pnl = -stake

            elif market == "spreads":
                line = safe_float(row["line"])
                diff = (away_score - home_score) if team == away else (home_score - away_score)
                adj = diff + line
                if adj > 0:
                    result = "won"
                    pnl = stake * (abs(odds) / 100)
                elif adj == 0:
                    result = "push"
                else:
                    result = "lost"
                    pnl = -stake

            elif market == "totals":
                line = safe_float(row["line"])
                total = away_score + home_score
                if team == "over":
                    if total > line:
                        result = "won"
                        pnl = stake * (abs(odds) / 100)
                    elif total == line:
                        result = "push"
                    else:
                        result = "lost"
                        pnl = -stake
                else:
                    if total < line:
                        result = "won"
                        pnl = stake * (abs(odds) / 100)
                    elif total == line:
                        result = "push"
                    else:
                        result = "lost"
                        pnl = -stake

            if result:
                row["status"] = "closed"
                row["result"] = result
                row["pnl"] = f"{pnl:.2f}"

    return history


# ============================================================
# SECTION 5: INJURY DATA
# ============================================================

def fetch_event_meta(api_key, sport):
    """Fetch event metadata (including injuries if available)."""
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/events"
    try:
        resp = requests.get(url, params={"apiKey": api_key}, timeout=10)
        if resp.status_code != 200:
            return {}
        events = resp.json()
        return {e["id"]: e for e in events if "id" in e}
    except Exception:
        return {}


def injury_penalty(meta, team):
    """
    Compute a penalty factor based on injury status for the given team.
    This reduces both the score and effective win probability.
    """
    injuries = meta.get("injuries")
    if not isinstance(injuries, list):
        return 0.0

    penalty = 0.0
    for inj in injuries:
        if normalize_str(inj.get("team")) != normalize_str(team):
            continue
        status = normalize_str(inj.get("status") or "")
        if status in ("out", "doubtful"):
            penalty += INJURY_HEAVY_PENALTY
        elif status == "questionable":
            penalty += INJURY_LIGHT_PENALTY
    return penalty


# ============================================================
# SECTION 6: FETCH + NORMALIZE + AVERAGE ODDS
# ============================================================

def fetch_all_odds(api_key):
    """
    Fetch odds for all configured sports and markets, normalize,
    and aggregate across bookmakers via average odds.
    """
    raw = []

    for sport in SPORTS.keys():
        meta_idx = fetch_event_meta(api_key, sport)

        url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
        params = {
            "apiKey": api_key,
            "regions": "us",
            "markets": ",".join(MARKETS),
            "oddsFormat": "american",
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                continue
            games = resp.json()
        except Exception:
            continue

        for g in games:
            away = g.get("away_team")
            home = g.get("home_team")
            if not away or not home:
                continue

            event = f"{away} @ {home}"
            ev_id = g.get("id")
            meta = meta_idx.get(ev_id, {})

            try:
                commence = g["commence_time"]
                game_time = datetime.fromisoformat(commence.replace("Z", "+00:00"))
            except Exception:
                game_time = None

            for bm in g.get("bookmakers", []):
                for mkt in bm.get("markets", []):
                    key = mkt.get("key")
                    if key not in MARKETS:
                        continue

                    for o in mkt.get("outcomes", []):
                        odds_val = o.get("price")
                        if odds_val is None:
                            continue

                        try:
                            odds_val = int(odds_val)
                        except Exception:
                            continue

                        if abs(odds_val) > MAX_ODDS:
                            continue

                        team = o.get("name", "")
                        line = o.get("point", 0)

                        if key == "totals":
                            nm = normalize_str(team)
                            if nm.startswith("over"):
                                team = "over"
                            elif nm.startswith("under"):
                                team = "under"

                        raw.append({
                            "sport": sport,
                            "event": event,
                            "market": key,
                            "team": team,
                            "line": line,
                            "odds": odds_val,
                            "time": game_time,
                            "meta": meta,
                        })

    # Aggregate by normalized key → average odds
    agg = {}
    for b in raw:
        norm_key = (
            normalize_str(b["sport"]),
            normalize_str(b["event"]),
            normalize_str(b["market"]),
            normalize_str(b["team"]),
            round(float(b["line"] or 0), 2),
        )

        if norm_key not in agg:
            agg[norm_key] = {
                "sport": b["sport"],
                "event": b["event"],
                "market": b["market"],
                "team": b["team"],
                "line": b["line"],
                "time": b["time"],
                "meta": b["meta"],
                "odds_sum": b["odds"],
                "odds_count": 1,
            }
        else:
            rec = agg[norm_key]
            rec["odds_sum"] += b["odds"]
            rec["odds_count"] += 1
            if rec["time"] is None and b["time"] is not None:
                rec["time"] = b["time"]

    deduped = []
    for rec in agg.values():
        avg_odds = int(round(rec["odds_sum"] / rec["odds_count"]))
        deduped.append({
            "sport": rec["sport"],
            "event": rec["event"],
            "market": rec["market"],
            "team": rec["team"],
            "line": rec["line"],
            "odds": avg_odds,
            "time": rec["time"],
            "meta": rec["meta"],
        })

    return deduped


# ============================================================
# SECTION 7: SCORING + WIN PROBABILITY
# ============================================================

def implied_prob(odds):
    """Convert American odds to implied probability (0–1)."""
    odds = int(odds)
    if odds == 0:
        return 0.0
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    return 100 / (odds + 100)


def implied_ev(odds):
    """A very simple EV-like score from implied probability."""
    p = implied_prob(odds)
    return 2 * p - 1


def score_bet(b):
    """
    Score a bet:
    - Start with implied EV from odds.
    - Subtract injury penalty.
    """
    base = implied_ev(b["odds"])
    inj = injury_penalty(b["meta"], b["team"])
    return base - inj


def adjusted_win_probability(b):
    """
    Implied win probability adjusted by injury penalty, clamped to [0, 1].
    """
    p = implied_prob(b["odds"])
    inj = injury_penalty(b["meta"], b["team"])
    adj = p * max(0.0, 1.0 - inj)
    return max(0.0, min(1.0, adj))


# ============================================================
# SECTION 8: ANALYTICS – STATS + STREAK
# ============================================================

def compute_stats(history, base_bankroll):
    """
    Compute lifetime stats and ROI from closed bets.
    Returns a dict with:
    - lifetime_bets
    - wins, losses, pushes
    - win_rate
    - lifetime_roi
    - sport_breakdown
    - bankroll (base_bankroll + total_pnl)
    """
    closed = [
        r for r in history
        if r.get("status") == "closed" and r.get("result") in ("won", "lost", "push")
    ]

    total_bets = len(closed)
    total_stake = sum(safe_float(r.get("bet_amount")) for r in closed)
    total_pnl = sum(safe_float(r.get("pnl")) for r in closed)

    wins = sum(1 for r in closed if r.get("result") == "won")
    losses = sum(1 for r in closed if r.get("result") == "lost")
    pushes = sum(1 for r in closed if r.get("result") == "push")

    denom = wins + losses
    win_rate = (wins / denom) if denom > 0 else 0.0
    roi = (total_pnl / total_stake) if total_stake > 0 else 0.0

    sport_breakdown = {}
    for r in closed:
        s = r.get("sport", "unknown")
        sb = sport_breakdown.setdefault(s, {
            "wins": 0,
            "losses": 0,
            "pushes": 0,
            "stake": 0.0,
            "pnl": 0.0,
            "roi": 0.0,
        })
        sb["stake"] += safe_float(r.get("bet_amount"))
        sb["pnl"] += safe_float(r.get("pnl"))
        if r.get("result") == "won":
            sb["wins"] += 1
        elif r.get("result") == "lost":
            sb["losses"] += 1
        elif r.get("result") == "push":
            sb["pushes"] += 1

    for s, sb in sport_breakdown.items():
        if sb["stake"] > 0:
            sb["roi"] = sb["pnl"] / sb["stake"]
        else:
            sb["roi"] = 0.0

    bankroll = base_bankroll + total_pnl

    return {
        "lifetime_bets": total_bets,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "win_rate": round(win_rate, 4),
        "lifetime_roi": round(roi, 4),
        "sport_breakdown": sport_breakdown,
        "bankroll": round(bankroll, 2),
    }


def compute_streak(history):
    """
    Compute current streak and max win/loss streaks from closed bets.
    current:
      - positive => consecutive wins
      - negative => consecutive losses
      - zero => neutral/no data
    """
    closed = [
        r for r in history
        if r.get("status") == "closed" and r.get("result") in ("won", "lost", "push")
    ]
    if not closed:
        return {"current": 0, "max_win_streak": 0, "max_loss_streak": 0}

    def parse_ts(r):
        try:
            return datetime.fromisoformat(r.get("timestamp"))
        except Exception:
            return datetime.min

    closed_sorted = sorted(closed, key=parse_ts)

    current = 0
    max_win = 0
    max_loss = 0

    for r in closed_sorted:
        result = r.get("result")
        if result == "won":
            if current >= 0:
                current += 1
            else:
                current = 1
            if current > max_win:
                max_win = current
        elif result == "lost":
            if current <= 0:
                current -= 1
            else:
                current = -1
            if current < max_loss:
                max_loss = current
        else:
            # push -> do not reset streak, but don't extend it
            continue

    return {
        "current": current,
        "max_win_streak": max_win,
        "max_loss_streak": max_loss,
    }


# ============================================================
# SECTION 9: MAIN EXECUTION
# ============================================================

def main():
    config = load_config()
    api_key = config["ODDS_API_KEY"]
    base_bankroll = float(config["BASE_BANKROLL"])
    stake_fraction = float(config["UNIT_FRACTION"])

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # One-time cleanup of old duplicate rows
    cleanup_history_once()

    # 1) Grade open bets
    history = read_history()
    history = grade_open_bets(api_key, history)

    # 2) Compute bankroll from full history PnL
    total_pnl = sum(
        safe_float(r.get("pnl"))
        for r in history
        if r.get("pnl") not in (None, "", " ")
    )
    bankroll = base_bankroll + total_pnl

    # 3) Count open bets
    open_bets = [r for r in history if r.get("status") == "open"]
    open_count = len(open_bets)

    # 4) Decide whether to generate new picks
    allow_new_picks = open_count < MAX_OPEN_BETS
    picks = []

    if allow_new_picks:
        bets = fetch_all_odds(api_key)

        scored = []
        for b in bets:
            s = score_bet(b)
            if s > 0:
                b["score"] = s
                scored.append(b)

        scored.sort(key=lambda x: x["score"], reverse=True)

        # Only fill remaining slots up to MAX_OPEN_BETS
        slots = MAX_OPEN_BETS - open_count
        picks = scored[:slots]

        # Build set of existing open bet keys to avoid duplicates
        existing_open_keys = {
            (
                normalize_str(r["sport"]),
                normalize_str(r["event"]),
                normalize_str(r["market"]),
                normalize_str(r["team"]),
                round(float(r["line"] or 0), 2),
                int(float(r["odds"])),
            )
            for r in history
            if r["status"] == "open"
        }

        stake = bankroll * stake_fraction if picks else 0.0

        for p in picks:
            key = (
                normalize_str(p["sport"]),
                normalize_str(p["event"]),
                normalize_str(p["market"]),
                normalize_str(p["team"]),
                round(float(p["line"] or 0), 2),
                int(p["odds"]),
            )
            if key in existing_open_keys:
                continue

            history.append({
                "timestamp": ts,
                "sport": p["sport"],
                "event": p["event"],
                "market": p["market"],
                "team": p["team"],
                "line": p["line"],
                "odds": str(p["odds"]),
                "bet_amount": f"{stake:.2f}",
                "status": "open",
                "result": "",
                "pnl": "",
            })

    # 5) Write updated history
    write_history(history)

    # 6) Compute analytics
    stats = compute_stats(history, base_bankroll)
    streak = compute_streak(history)

    # 7) Build JSON picks
    json_picks = []
    for p in picks:
        t = p["time"]
        t_str = None
        if isinstance(t, datetime):
            t_str = t.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        json_picks.append({
            "sport": p["sport"],
            "event": p["event"],
            "market": p["market"],
            "team": p["team"],
            "line": p["line"],
            "odds": p["odds"],
            "score": round(p["score"], 4),
            "win_probability": round(adjusted_win_probability(p), 4),
            "game_time": t_str,
        })

    output = {
        "bankroll": stats["bankroll"],
        "last_updated": ts,
        "open_bets": [r for r in history if r["status"] == "open"],
        "todays_picks": json_picks,
        "new_picks_generated": allow_new_picks,
        "stats": stats,
        "streak": streak,
    }

    with open(DATA_FILE, "w") as f:
        json.dump(output, f, indent=2)

    # 8) Git push
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", f"SmartPicks update {ts}"], check=True)
        subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print("[WARN] Git push failed:", e)


if __name__ == "__main__":
    main()
