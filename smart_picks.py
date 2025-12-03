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

MAX_ODDS = 200
TOP_N = 10
INJURY_HEAVY_PENALTY = 0.30
INJURY_LIGHT_PENALTY = 0.15


# -------------------------------------------------------------
# FILE HELPERS
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


# -------------------------------------------------------------
# GRADING
# -------------------------------------------------------------

def fetch_scores(api_key, sport, days=3):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/scores"
    params = {"apiKey": api_key, "daysFrom": days}
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return []
        return resp.json()
    except:
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
            except:
                return 0
    return 0


def grade_open_bets(api_key, history):
    if not history:
        return history, 0.0

    bankroll_delta = 0.0

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
    except:
        return {}


def injury_penalty(meta, team):
    injuries = meta.get("injuries")
    if not isinstance(injuries, list):
        return 0.0

    p = 0.0
    for inj in injuries:
        if inj.get("team") != team:
            continue
        s = (inj.get("status") or "").lower()
        if s in ("out", "doubtful"):
            p += INJURY_HEAVY_PENALTY
        elif s == "questionable":
            p += INJURY_LIGHT_PENALTY
    return p


# -------------------------------------------------------------
# ODDS FETCHING + API DEDUPE
# -------------------------------------------------------------

def fetch_all_odds(api_key):
    bets = []

    for sport in SPORTS.keys():
        meta = fetch_event_meta(api_key, sport)

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
        except:
            continue

        for g in games:
            away = g.get("away_team")
            home = g.get("home_team")
            if not away or not home:
                continue

            event = f"{away} @ {home}"
            eid = g.get("id")
            meta_e = meta.get(eid, {})

            try:
                t = datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00"))
            except:
                t = None

            for bm in g.get("bookmakers", []):
                for mkt in bm.get("markets", []):
                    key = mkt.get("key")
                    if key not in MARKETS:
                        continue

                    for o in mkt.get("outcomes", []):
                        odds = o.get("price")
                        if odds is None:
                            continue

                        try:
                            odds = int(odds)
                        except:
                            continue

                        if abs(odds) > MAX_ODDS:
                            continue

                        team = o.get("name", "")
                        line = o.get("point", 0)

                        if key == "totals":
                            team = "over" if team.lower().startswith("over") else \
                                   "under" if team.lower().startswith("under") else team

                        bets.append({
                            "sport": sport,
                            "event": event,
                            "market": key,
                            "team": team,
                            "line": line,
                            "odds": odds,
                            "time": t,
                            "meta": meta_e,
                        })

    # --- Dedupe across bookmakers ---
    unique = {}
    for b in bets:
        k = (
            b["sport"], b["event"], b["market"], b["team"],
            str(b["line"]), str(b["odds"])
        )
        if k not in unique:
            unique[k] = b

    return list(unique.values())


# -------------------------------------------------------------
# SCORING
# -------------------------------------------------------------

def implied_ev(odds):
    if odds < 0:
        p = abs(odds) / (abs(odds) + 100)
    else:
        p = 100 / (odds + 100)
    return 2 * p - 1


def score_bet(b):
    base = implied_ev(b["odds"])
    inj = injury_penalty(b["meta"], b["team"])
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

    history = read_history()
    history, delta = grade_open_bets(api_key, history)
    bankroll += delta

    bets = fetch_all_odds(api_key)

    scored = []
    for b in bets:
        s = score_bet(b)
        if s > 0:
            b["score"] = s
            scored.append(b)

    scored.sort(key=lambda x: x["score"], reverse=True)
    picks = scored[:TOP_N]

    # --- Logging dedupe ---
    existing = {
        (
            r["sport"], r["event"], r["market"],
            r["team"], str(r["line"]), str(r["odds"])
        )
        for r in history
        if r["status"] == "open"
    }

    stake = bankroll * unit_fraction if picks else 0.0

    for p in picks:
        key = (
            p["sport"], p["event"], p["market"],
            p["team"], str(p["line"]), str(p["odds"])
        )

        if key in existing:
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

    # JSON output
    json_picks = []
    for p in picks:
        t = p["time"]
        t = t.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if isinstance(t, datetime) else None

        json_picks.append({
            "sport": p["sport"],
            "event": p["event"],
            "market": p["market"],
            "team": p["team"],
            "line": p["line"],
            "odds": p["odds"],
            "score": round(p["score"], 4),
            "game_time": t,
        })

    output = {
        "bankroll": round(bankroll, 2),
        "last_updated": ts,
        "open_bets": [r for r in history if r["status"] == "open"],
        "todays_picks": json_picks,
    }

    with open(DATA_FILE, "w") as f:
        json.dump(output, f, indent=2)

    # Git push
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", f"SmartPicks update {ts}"], check=True)
        subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print("[WARN] Git push failed:", e)


if __name__ == "__main__":
    main()
