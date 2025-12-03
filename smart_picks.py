#!/usr/bin/env python3

import csv
import json
import os
import subprocess
from datetime import datetime, timezone
import requests

# -------------------------------------------------------------
# CONFIG / CONSTANTS
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

# Risk tuning
MAX_ODDS = 200          # avoid crazy juice
TOP_N = 10              # up to 10 picks
INJURY_HEAVY_PENALTY = 0.30
INJURY_LIGHT_PENALTY = 0.15


# -------------------------------------------------------------
# CONFIG / FILE HELPERS
# -------------------------------------------------------------

def load_config():
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def ensure_history_file():
    """Create bet_history.csv with header if it doesn't exist."""
    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "sport", "event", "market", "team", "line",
                "odds", "bet_amount", "status", "result", "pnl"
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
    """Rewrite bet_history.csv with updated rows. Safe if rows is non-empty."""
    if not rows:
        # Nothing to write, but file already has header from ensure_history_file()
        return
    with open(HISTORY_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


# -------------------------------------------------------------
# BET GRADING
# -------------------------------------------------------------

def fetch_scores_for_sport(api_key, sport_key, days_from=3):
    """Fetch scores for a given sport (last N days)."""
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/scores"
    params = {"apiKey": api_key, "daysFrom": days_from}
    try:
        resp = requests.get(url, params=params, timeout=10)
    except Exception:
        return []

    if resp.status_code != 200:
        return []

    try:
        return resp.json()
    except Exception:
        return []


def index_scores_by_event(scores):
    """
    Build an index: "Away @ Home" -> game object
    Based on away_team/home_team and scores list.
    """
    index = {}
    for g in scores:
        away = g.get("away_team")
        home = g.get("home_team")
        if not away or not home:
            continue
        label = f"{away} @ {home}"
        index[label] = g
    return index


def extract_scores(game):
    """
    Return (away_score, home_score) as ints, or (None, None) if not available.
    """
    scores = game.get("scores")
    if not isinstance(scores, list) or len(scores) < 2:
        return None, None

    # Try to map by team name if possible
    away_name = game.get("away_team")
    home_name = game.get("home_team")
    score_map = {}
    for s in scores:
        name = s.get("name")
        try:
            val = int(s.get("score", 0))
        except (TypeError, ValueError):
            val = None
        if name:
            score_map[name] = val

    away_score = score_map.get(away_name)
    home_score = score_map.get(home_name)

    # Fallback: if mapping failed, try positional
    if away_score is None or home_score is None:
        try:
            away_score = int(scores[0].get("score", 0))
            home_score = int(scores[1].get("score", 0))
        except Exception:
            return None, None

    return away_score, home_score


def grade_open_bets(api_key, history_rows):
    """
    Grade all open bets using scores from The Odds API.
    Returns (updated_rows, bankroll_delta).
    """
    if not history_rows:
        return history_rows, 0.0

    # Group open bets by sport
    open_by_sport = {}
    for row in history_rows:
        if row.get("status") == "open":
            sport = row.get("sport")
            if sport:
                open_by_sport.setdefault(sport, []).append(row)

    if not open_by_sport:
        return history_rows, 0.0

    bankroll_delta = 0.0

    for sport, rows in open_by_sport.items():
        scores = fetch_scores_for_sport(api_key, sport, days_from=3)
        if not scores:
            continue

        score_index = index_scores_by_event(scores)

        for row in rows:
            event_label = row.get("event")
            game = score_index.get(event_label)
            if not game:
                continue

            if not game.get("completed", False):
                continue

            away_score, home_score = extract_scores(game)
            if away_score is None or home_score is None:
                continue

            market = row.get("market")
            bet_team = row.get("team")
            try:
                odds = float(row.get("odds", 0))
                stake = float(row.get("bet_amount", 0))
            except ValueError:
                continue

            result = None
            pnl = 0.0

            # h2h grading
            if market == "h2h":
                away_team = game.get("away_team")
                home_team = game.get("home_team")
                if away_score > home_score:
                    winner = away_team
                elif home_score > away_score:
                    winner = home_team
                else:
                    winner = None  # unlikely in moneyline context

                if winner is None:
                    result = "push"
                    pnl = 0.0
                else:
                    if bet_team == winner:
                        result = "won"
                        pnl = stake * (abs(odds) / 100.0)
                    else:
                        result = "lost"
                        pnl = -stake

            # spreads grading
            elif market == "spreads":
                try:
                    line = float(row.get("line", 0))
                except ValueError:
                    line = 0.0

                away_team = game.get("away_team")
                home_team = game.get("home_team")

                if bet_team == away_team:
                    diff = away_score - home_score
                elif bet_team == home_team:
                    diff = home_score - away_score
                else:
                    # Unknown mapping, skip
                    continue

                adjusted = diff + line
                if adjusted > 0:
                    result = "won"
                    pnl = stake * (abs(odds) / 100.0)
                elif adjusted == 0:
                    result = "push"
                    pnl = 0.0
                else:
                    result = "lost"
                    pnl = -stake

            # totals grading
            elif market == "totals":
                try:
                    line = float(row.get("line", 0))
                except ValueError:
                    line = 0.0

                total = away_score + home_score

                if bet_team == "over":
                    if total > line:
                        result = "won"
                        pnl = stake * (abs(odds) / 100.0)
                    elif total == line:
                        result = "push"
                        pnl = 0.0
                    else:
                        result = "lost"
                        pnl = -stake
                elif bet_team == "under":
                    if total < line:
                        result = "won"
                        pnl = stake * (abs(odds) / 100.0)
                    elif total == line:
                        result = "push"
                        pnl = 0.0
                    else:
                        result = "lost"
                        pnl = -stake

            # If we graded it, update row
            if result is not None:
                row["status"] = "closed"
                row["result"] = result
                row["pnl"] = f"{pnl:.2f}"
                bankroll_delta += pnl

    return history_rows, bankroll_delta


# -------------------------------------------------------------
# INJURY PENALTY
# -------------------------------------------------------------

def build_event_meta(api_key, sport_key):
    """
    Fetch event metadata (including injuries if available) and index by event id.
    """
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events"
    params = {"apiKey": api_key}
    try:
        resp = requests.get(url, params=params, timeout=10)
    except Exception:
        return {}

    if resp.status_code != 200:
        return {}

    try:
        events = resp.json()
    except Exception:
        return {}

    meta_index = {}
    for e in events:
        eid = e.get("id")
        if eid:
            meta_index[eid] = e
    return meta_index


def injury_penalty(event_data, team_name):
    """
    Calculate a simple injury penalty based on event metadata.
    If injuries aren't present, returns 0.
    """
    if not isinstance(event_data, dict):
        return 0.0

    injuries = event_data.get("injuries")
    if not isinstance(injuries, list):
        return 0.0

    penalty = 0.0
    for inj in injuries:
        if inj.get("team") != team_name:
            continue
        status = (inj.get("status") or "").lower()
        if status in ("out", "doubtful"):
            penalty += INJURY_HEAVY_PENALTY
        elif status in ("questionable",):
            penalty += INJURY_LIGHT_PENALTY

    return penalty


# -------------------------------------------------------------
# ODDS FETCHING
# -------------------------------------------------------------

def fetch_all_odds(api_key):
    """
    Fetch odds for all configured sports/markets.
    Returns a flat list of candidate bets.
    """
    all_bets = []

    for sport_key in SPORTS.keys():
        # Main odds
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
        params = {
            "apiKey": api_key,
            "regions": "us",
            "markets": ",".join(MARKETS),
            "oddsFormat": "american",
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
        except Exception:
            continue

        if resp.status_code != 200:
            continue

        try:
            data = resp.json()
        except Exception:
            continue

        # Event metadata (for injuries, etc.)
        meta_index = build_event_meta(api_key, sport_key)

        for g in data:
            event_id = g.get("id")
            meta = meta_index.get(event_id, {})

            away = g.get("away_team")
            home = g.get("home_team")
            if not away or not home:
                continue

            match_label = f"{away} @ {home}"

            # Game time
            commence = g.get("commence_time")
            try:
                game_time = datetime.fromisoformat(commence.replace("Z", "+00:00"))
            except Exception:
                game_time = None

            for bookmaker in g.get("bookmakers", []):
                for market in bookmaker.get("markets", []):
                    mkt_key = market.get("key")
                    if mkt_key not in MARKETS:
                        continue

                    for outcome in market.get("outcomes", []):
                        odds = outcome.get("price")
                        if odds is None:
                            continue

                        # basic juice control
                        try:
                            odds_val = int(odds)
                        except (TypeError, ValueError):
                            continue

                        if abs(odds_val) > MAX_ODDS:
                            continue

                        team_name = outcome.get("name") or ""
                        point = outcome.get("point", 0)

                        # For totals, normalize team_name to "over"/"under"
                        if mkt_key == "totals":
                            if team_name.lower().startswith("over"):
                                team_name = "over"
                            elif team_name.lower().startswith("under"):
                                team_name = "under"

                        all_bets.append({
                            "sport": sport_key,
                            "event": match_label,
                            "market": mkt_key,
                            "team": team_name,
                            "line": point,
                            "odds": odds_val,
                            "game_time": game_time,
                            "event_meta": meta,
                        })

    return all_bets


# -------------------------------------------------------------
# SCORING / EV
# -------------------------------------------------------------

def compute_ev_like_score(odds):
    """
    Simple monotonic "EV-like" score based on implied probability.
    This is NOT true $ EV, but good enough to rank safely.
    """
    if odds == 0:
        return 0.0

    if odds < 0:
        prob = abs(odds) / (abs(odds) + 100)
    else:
        prob = 100 / (odds + 100)

    # scale to [-1, 1]
    return 2 * prob - 1


def score_bet(bet):
    """
    Combine EV-like score and injury penalty.
    Fatigue is intentionally 0.0 for v0.1.1 to stay simple & robust.
    """
    odds = bet.get("odds", 0)
    base = compute_ev_like_score(odds)

    # Fatigue not implemented yet (placeholder)
    fatigue = 0.0

    # Injury penalty
    # Note: For now we apply injuries to the "team" field only.
    inj = injury_penalty(bet.get("event_meta", {}), bet.get("team"))

    return base - fatigue - inj


# -------------------------------------------------------------
# MAIN
# -------------------------------------------------------------

def main():
    # Load config
    config = load_config()
    api_key = config["ODDS_API_KEY"]
    bankroll = float(config.get("BASE_BANKROLL", 200.0))
    unit_fraction = float(config.get("UNIT_FRACTION", 0.01))

    # Timestamp (UTC)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # 1) Load + grade previous bets
    history = read_history()
    history, delta = grade_open_bets(api_key, history)
    bankroll += delta

    # 2) Fetch candidate bets from Odds API
    bets = fetch_all_odds(api_key)

    # 3) Score and filter bets
    scored = []
    for bet in bets:
        score = score_bet(bet)
        if score > 0:  # keep only "safe-ish" bets
            bet["score"] = score
            scored.append(bet)

    # 4) Sort and select up to TOP_N picks
    scored.sort(key=lambda b: b["score"], reverse=True)
    picks = scored[:TOP_N]

    # 5) Log new bets into history
    stake = bankroll * unit_fraction if picks else 0.0

    for p in picks:
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

    # 6) Write updated history
    write_history(history)

    # 7) Build JSON-safe picks (no datetime objects)
    json_picks = []
    for p in picks:
        game_time_str = None
        if isinstance(p.get("game_time"), datetime):
            game_time_str = p["game_time"].astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        json_picks.append({
            "sport": p["sport"],
            "event": p["event"],
            "market": p["market"],
            "team": p["team"],
            "line": p["line"],
            "odds": p["odds"],
            "score": round(p.get("score", 0.0), 4),
            "game_time": game_time_str,
        })

    open_bets = [r for r in history if r.get("status") == "open"]

    output = {
        "bankroll": round(bankroll, 2),
        "last_updated": ts,
        "open_bets": open_bets,
        "todays_picks": json_picks,
    }

    with open(DATA_FILE, "w") as f:
        json.dump(output, f, indent=2)

    # 8) Try git commit & push (but don't crash if it fails)
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", f"SmartPicks update {ts}"], check=True)
        subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print("[WARN] Git push failed:", e)


if __name__ == "__main__":
    main()
