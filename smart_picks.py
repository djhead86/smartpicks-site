#!/usr/bin/env python3
"""
Patched Smart Picks Backend (smart_picks.py)
--------------------------------------------

Features:
- Fetches odds for all configured sports
- Event-level dedupe
- Score scraping (all sports), automatic grading
- Manual override merging (Strategy 3)
- bet_history.csv maintenance
- Output: data.json, scores.json, analytics block
- Full history array for frontend (aligned with JS)
"""

import os
import csv
import json
import math
import requests
from datetime import datetime, timezone, timedelta

# -------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------
CONFIG_PATH = "config.json"
BET_HISTORY_PATH = "bet_history.csv"
DATA_PATH = "data.json"
SCORES_PATH = "scores.json"
MANUAL_OVERRIDES_PATH = "manual_overrides.json"

SPORTS = [
    "basketball_nba",
    "americanfootball_nfl",
    "americanfootball_ncaaf",
    "icehockey_nhl",
    "baseball_mlb",
    "soccer_epl",
    "mma_mixed_martial_arts"
]

MARKETS = ["h2h", "spreads", "totals"]
API_BASE = "https://api.the-odds-api.com/v4/sports"

MAX_KELLY = 0.02  # 2%


# -------------------------------------------------------------
# LOAD CONFIG
# -------------------------------------------------------------
def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise RuntimeError("config.json missing.")

    with open(CONFIG_PATH, "r") as f:
        cfg = json.load(f)

    if not cfg.get("ODDS_API_KEY"):
        raise RuntimeError("ODDS_API_KEY missing.")

    cfg.setdefault("BASE_BANKROLL", 200.0)
    cfg.setdefault("UNIT_FRACTION", 0.01)

    return cfg


# -------------------------------------------------------------
# TIME UTILS
# -------------------------------------------------------------
def now_iso():
    return datetime.now(timezone.utc).isoformat()


# -------------------------------------------------------------
# ODDS HELPERS
# -------------------------------------------------------------
def american_to_prob(odds):
    odds = float(odds)
    if odds < 0:
        return -odds / (-odds + 100)
    return 100 / (odds + 100)


def kelly(p, odds):
    if odds < 0:
        b = 100 / abs(odds)
    else:
        b = odds / 100
    q = 1 - p
    k = (b * p - q) / b
    return max(0, k)


# -------------------------------------------------------------
# FETCH ODDS FOR ONE SPORT
# -------------------------------------------------------------
def fetch_odds(api_key, sport):
    url = f"{API_BASE}/{sport}/odds"
    params = {
        "apiKey": api_key,
        "regions": "us",
        "markets": ",".join(MARKETS),
        "oddsFormat": "american",
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


# -------------------------------------------------------------
# BUILD BET ID
# -------------------------------------------------------------
def make_bet_id(sport, match, team, market, event_time):
    raw = f"{sport}_{match}_{team}_{market}_{event_time}"
    return "".join(c if c.isalnum() or c == "_" else "_" for c in raw)


# -------------------------------------------------------------
# PARSE CANDIDATES
# -------------------------------------------------------------
def parse_sport_books(odds_json, sport, bankroll, unit_fraction):
    picks = []

    for game in odds_json:
        home = game.get("home_team", "Home")
        away = game.get("away_team", "Away")
        match = f"{away} @ {home}"

        event_time = game.get("commence_time", "")

        bookmakers = game.get("bookmakers", [])
        if not bookmakers:
            continue

        # First bookmaker only (cleanest)
        bm = bookmakers[0]

        for market_info in bm.get("markets", []):
            market = market_info.get("key")
            if market not in MARKETS:
                continue

            for out in market_info.get("outcomes", []):
                team = out.get("name")
                price = out.get("price")
                if price is None:
                    continue

                price = float(price)
                implied = american_to_prob(price)

                # Simple model boost
                model_p = min(0.99, max(0.01, implied + 0.01))

                ev = None
                if price < 0:
                    b = 100 / abs(price)
                else:
                    b = price / 100
                ev = model_p * b - (1 - model_p)

                k = kelly(model_p, price)
                k = min(MAX_KELLY, k, unit_fraction)
                stake = round(bankroll * k, 2)

                bet_id = make_bet_id(sport, match, team, market, event_time)

                picks.append({
                    "bet_id": bet_id,
                    "sport": sport,
                    "match": match,
                    "team": team,
                    "market": market,
                    "price": price,
                    "implied_prob": implied,
                    "model_prob": model_p,
                    "ev": ev,
                    "recommended_fraction": k,
                    "recommended_stake": stake,
                    "event_time": event_time
                })

    return picks


# -------------------------------------------------------------
# DEDUPE
# -------------------------------------------------------------
def dedupe_picks(picks):
    best = {}
    for p in picks:
        key = (p["sport"], p["match"], p["team"], p["market"])
        if key not in best or p["ev"] > best[key]["ev"]:
            best[key] = p
    return list(best.values())


# -------------------------------------------------------------
# SCORE FETCHING FOR ALL SPORTS
# -------------------------------------------------------------
def fetch_scores(api_key):
    url = "https://api.the-odds-api.com/v4/scores/"
    params = {"apiKey": api_key, "daysFrom": 3}
    r = requests.get(url, params=params, timeout=20)
    if r.status_code != 200:
        return []
    return r.json()


def write_scores(scores):
    with open(SCORES_PATH, "w") as f:
        json.dump(scores, f, indent=2)


# -------------------------------------------------------------
# HISTORY CSV LOAD & SAVE
# -------------------------------------------------------------
def load_history_csv():
    if not os.path.exists(BET_HISTORY_PATH):
        return []

    rows = []
    with open(BET_HISTORY_PATH, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def save_history_csv(rows):
    fieldnames = [
        "bet_id", "timestamp", "date", "sport", "match", "team", "market",
        "odds", "stake", "event_time", "status", "result", "profit", "bankroll_after"
    ]
    with open(BET_HISTORY_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


# -------------------------------------------------------------
# AUTOMATIC RESULT GRADING
# -------------------------------------------------------------
def grade_bet_auto(row, scores):
    """Return updated row after auto-grading, or unchanged row."""
    
    # Skip legacy entries missing required fields
    match = row.get("match")
    sport = row.get("sport")
    team = row.get("team")
    market = row.get("market")

    if not match or not sport or not team or not market:
        # Incomplete row – leave as-is
        return row

    for s in scores:
        if s.get("sport") == sport and s.get("home_team") and s.get("away_team"):
            home = s["home_team"]
            away = s["away_team"]
            if home in match or away in match:
                if not s.get("completed"):
                    return row  # not final yet

                winner = s.get("winner", "")
                if not winner:
                    return row

                odds = float(row["odds"])
                stake = float(row["stake"])

                if market == "h2h":
                    if team == winner:
                        profit = stake * (100 / abs(odds)) if odds < 0 else stake * (odds / 100)
                        row["result"] = "WIN"
                    else:
                        profit = -stake
                        row["result"] = "LOSS"

                    row["profit"] = round(profit, 2)
                    row["status"] = "CLOSED"
                    return row

                # Spread & totals → manual grading only
                return row

    return row


                # For spreads/totals, auto-scoring unreliable; leave manual
    return row

    return row


# -------------------------------------------------------------
# MANUAL OVERRIDES (Strategy 3)
# -------------------------------------------------------------
def load_manual_overrides():
    if not os.path.exists(MANUAL_OVERRIDES_PATH):
        return {}
    with open(MANUAL_OVERRIDES_PATH, "r") as f:
        return json.load(f)


def apply_manual_override(row, overrides):
    if row["result"] != "PENDING":
        return row

    bid = row["bet_id"]
    if bid not in overrides:
        return row

    manual = overrides[bid]
    row["result"] = manual

    stake = float(row["stake"])
    odds = float(row["odds"])

    if manual == "PUSH":
        row["profit"] = 0.0
    elif manual == "WIN":
        row["profit"] = (
            stake * (100 / abs(odds)) if odds < 0 else stake * (odds / 100)
        )
    else:
        row["profit"] = -stake

    row["profit"] = round(row["profit"], 2)
    row["status"] = "CLOSED"
    return row

# -------------------------------------------------------------
# ANALYTICS GENERATION
# -------------------------------------------------------------
def compute_analytics(history_rows):
    if not history_rows:
        return {
            "total_bets": 0,
            "wins": 0,
            "losses": 0,
            "pushes": 0,
            "roi": 0,
            "sport_roi": {},
            "bankroll_history": []
        }

    wins = 0
    losses = 0
    pushes = 0
    profit_sum = 0.0

    sport_profit = {}
    sport_stake = {}

    bankroll_curve = []
    running_bankroll = 0.0

    for row in history_rows:
        res = row["result"]
        profit = float(row["profit"])
        stake = float(row["stake"])
        sport = row["sport"]

        if res == "WIN":
            wins += 1
        elif res == "LOSS":
            losses += 1
        elif res == "PUSH":
            pushes += 1

        profit_sum += profit

        sport_profit.setdefault(sport, 0.0)
        sport_stake.setdefault(sport, 0.0)
        sport_profit[sport] += profit
        sport_stake[sport] += stake

        running_bankroll += profit
        bankroll_curve.append({
            "t": row["timestamp"],
            "bankroll": round(running_bankroll, 2)
        })

    roi = (profit_sum / sum(sport_stake.values())) if sum(sport_stake.values()) > 0 else 0

    sport_roi = {}
    for sp in sport_profit:
        if sport_stake[sp] > 0:
            sport_roi[sp] = sport_profit[sp] / sport_stake[sp]
        else:
            sport_roi[sp] = 0

    return {
        "total_bets": len(history_rows),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "roi": roi,
        "sport_roi": sport_roi,
        "bankroll_history": bankroll_curve
    }


# -------------------------------------------------------------
# EXPORT FRONTEND JSON
# -------------------------------------------------------------
def export_data_json(picks, history_rows, analytics):
    data = {
        "generated": now_iso(),
        "picks": picks,
        "history": history_rows,
        "analytics": analytics
    }
    with open(DATA_PATH, "w") as f:
        json.dump(data, f, indent=2)


    # -----------------------------
    # FETCH ODDS & BUILD PICKS
    # -----------------------------
    all_picks = []
    for sport in SPORTS:
        try:
            odds_json = fetch_odds(api_key, sport)
            sport_picks = parse_sport_books(
                odds_json, sport, bankroll, unit_fraction
            )
            all_picks.extend(sport_picks)
        except Exception as e:
            print(f"[WARN] Failed fetching odds for {sport}: {e}")

    # Dedupe event-level
    all_picks = dedupe_picks(all_picks)

    # -----------------------------
    # BUILD HISTORY ENTRY FOR NEW PICKS
    # -----------------------------
    now_date = datetime.now().strftime("%m/%d/%y")
    now_stamp = now_iso()

    # Determine starting bankroll for new entries
    if history_rows:
        last_bankroll = float(history_rows[-1].get("bankroll_after", bankroll))
    else:
        last_bankroll = bankroll

    for p in all_picks:
        # Only add new bet if not already present
        if not any(hr.get("bet_id") == p["bet_id"] for hr in history_rows):
            history_rows.append({
                "bet_id": p["bet_id"],
                "timestamp": now_stamp,
                "date": now_date,
                "sport": p["sport"],
                "match": p["match"],
                "team": p["team"],
                "market": p["market"],
                "odds": p["price"],
                "stake": p["recommended_stake"],
                "event_time": p["event_time"],
                "status": "OPEN",
                "result": "PENDING",
                "profit": 0.0,
                "bankroll_after": last_bankroll
            })

    save_history_csv(history_rows)

    # -----------------------------
    # ANALYTICS
    # -----------------------------
    analytics = compute_analytics(history_rows)

    # -----------------------------
    # EXPORT JSON FOR FRONTEND
    # -----------------------------
    export_data_json(all_picks, history_rows, analytics)

    print("[INFO] Data export complete.")
    print("[INFO] Done.")
