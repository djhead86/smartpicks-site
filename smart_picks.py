#!/usr/bin/env python3

import csv
import json
import os
import subprocess
from datetime import datetime, timezone
import requests

# -------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------

CONFIG_FILE = "config.json"
HISTORY_FILE = "bet_history.csv"
DATA_FILE = "data.json"

SPORTS = {
    "basketball_nba": "NBA",
    "americanfootball_nfl": "NFL",
    "icehockey_nhl": "NHL",
}

MARKETS = ["h2h", "spreads", "totals"]

MAX_ODDS = 200          # avoid huge juice
TOP_N = 10              # up to 10 picks per run
INJURY_HEAVY_PENALTY = 0.30
INJURY_LIGHT_PENALTY = 0.15


# -------------------------------------------------------------
# BASIC HELPERS
# -------------------------------------------------------------

def load_config():
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def ensure_history_file():
    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "sport", "event", "market", "team",
                "line", "odds", "bet_amount", "status", "result", "pnl"
            ])


def read_history():
    ensure_history_file()
    rows = []
    with open(HISTORY_FILE, "r") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


def write_history(rows):
    if not rows:
        return
    with open(HISTORY_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def normalize_str(s: str) -> str:
    """Lowercase, strip, collapse internal whitespace."""
    if s is None:
        return ""
    return " ".join(str(s).strip().lower().split())


# -------------------------------------------------------------
# GRADING PREVIOUS BETS
# -------------------------------------------------------------

def fetch_scores(api_key, sport, days=3):
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
    idx = {}
    for g in scores:
        away = g.get("away_team")
        home = g.get("home_team")
        if away and home:
            idx[f"{away} @ {home}"] = g
    return idx


def parse_score(game, team):
    scores = game.get("scores", [])
    for s in scores:
        if s.get("name") == team:
            try:
                return int(s.get("score"))
            except Exception:
                return 0
    return 0


def grade_open_bets(api_key, history):
    """Grade all open bets and return (updated_history, bankroll_delta)."""
    if not history:
        return history, 0.0

    bankroll_delta = 0.0

    # Group open bets by sport
    open_by_sport = {}
    for r in history:
        if r.get("status") == "open":
            sport = r["sport"]
            open_by_sport.setdefault(sport, []).append(r)

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
            odds = float(row["odds"])
            stake = float(row["bet_amount"])

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
                line = float(row["line"])
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
                line = float(row["line"])
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
                else:  # under
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
                bankroll_delta += pnl

    return history, bankroll_delta


# -------------------------------------------------------------
# INJURY DATA
# -------------------------------------------------------------

def fetch_event_meta(api_key, sport):
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


# -------------------------------------------------------------
# FETCH ODDS + NORMALIZED DEDUPE (AVG ODDS)
# -------------------------------------------------------------

def fetch_all_odds(api_key):
    """
    Fetch odds from The Odds API for all sports and markets,
    then normalize and aggregate duplicates (averaging odds across books).
    """
    raw_bets = []

    for sport in SPORTS.keys():
        meta_index = fetch_event_meta(api_key, sport)

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

            event_label = f"{away} @ {home}"
            event_id = g.get("id")
            meta = meta_index.get(event_id, {})

            commence = g.get("commence_time")
            try:
                game_time = datetime.fromisoformat(commence.replace("Z", "+00:00"))
            except Exception:
                game_time = None

            for bm in g.get("bookmakers", []):
                for mkt in bm.get("markets", []):
                    market_key = mkt.get("key")
                    if market_key not in MARKETS:
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

                        if market_key == "totals":
                            nm = normalize_str(team)
                            if nm.startswith("over"):
                                team = "over"
                            elif nm.startswith("under"):
                                team = "under"

                        raw_bets.append({
                            "sport": sport,
                            "event": event_label,
                            "market": market_key,
                            "team": team,
                            "line": line,
                            "odds": odds_val,
                            "time": game_time,
                            "meta": meta,
                        })

    # --- NORMALIZE & AGGREGATE (Average odds across books) ---
    agg = {}
    for b in raw_bets:
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
            # choose earliest game time if both present
            if rec["time"] is None and b["time"] is not None:
                rec["time"] = b["time"]

    # Build final list with averaged odds
    deduped_bets = []
    for rec in agg.values():
        avg_odds = int(round(rec["odds_sum"] / rec["odds_count"]))
        deduped_bets.append({
            "sport": rec["sport"],
            "event": rec["event"],
            "market": rec["market"],
            "team": rec["team"],
            "line": rec["line"],
            "odds": avg_odds,
            "time": rec["time"],
            "meta": rec["meta"],
        })

    return deduped_bets


# -------------------------------------------------------------
# SCORING
# -------------------------------------------------------------

def implied_ev(odds):
    """Simple EV-like score based on implied probability."""
    if odds == 0:
        return 0.0
    if odds < 0:
        p = abs(odds) / (abs(odds) + 100)
    else:
        p = 100 / (odds + 100)
    return 2 * p - 1  # maps [0,1] -> [-1,1]


def score_bet(bet):
    base = implied_ev(bet["odds"])
    inj = injury_penalty(bet["meta"], bet["team"])
    # fatigue placeholder = 0.0 for now
    return base - inj


# -------------------------------------------------------------
# MAIN
# -------------------------------------------------------------

def main():
    config = load_config()
    api_key = config["ODDS_API_KEY"]
    bankroll = float(config["BASE_BANKROLL"])
    unit_fraction = float(config["UNIT_FRACTION"])

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # 1) Grade existing open bets
    history = read_history()
    history, delta = grade_open_bets(api_key, history)
    bankroll += delta

    # 2) Fetch odds and aggregate
    bets = fetch_all_odds(api_key)

    # 3) Score and filter safe-ish bets
    scored = []
    for b in bets:
        s = score_bet(b)
        if s > 0:
            b["score"] = s
            scored.append(b)

    scored.sort(key=lambda x: x["score"], reverse=True)
    picks = scored[:TOP_N]

    # 4) Prevent logging duplicates into history
    existing_open = {
        (
            r["sport"], r["event"], r["market"],
            r["team"], str(r["line"]), str(r["odds"])
        )
        for r in history
        if r.get("status") == "open"
    }

    stake = bankroll * unit_fraction if picks else 0.0

    for p in picks:
        key = (
            p["sport"], p["event"], p["market"],
            p["team"], str(p["line"]), str(p["odds"])
        )
        if key in existing_open:
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

    write_history(history)

    # 5) Build JSON-safe picks
    json_picks = []
    for p in picks:
        game_time_str = None
        if isinstance(p["time"], datetime):
            game_time_str = p["time"].astimezone(timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        json_picks.append({
            "sport": p["sport"],
            "event": p["event"],
            "market": p["market"],
            "team": p["team"],
            "line": p["line"],
            "odds": p["odds"],
            "score": round(p["score"], 4),
            "game_time": game_time_str,
        })

    output = {
        "bankroll": round(bankroll, 2),
        "last_updated": ts,
        "open_bets": [r for r in history if r["status"] == "open"],
        "todays_picks": json_picks,
    }

    with open(DATA_FILE, "w") as f:
        json.dump(output, f, indent=2)

    # 6) Git add/commit/push (non-fatal)
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", f"SmartPicks update {ts}"], check=True)
        subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print("[WARN] Git push failed:", e)


if __name__ == "__main__":
    main()
