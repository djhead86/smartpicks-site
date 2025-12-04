#!/usr/bin/env python3
"""
Clean SmartPicks backend.

- Loads config.json with:
    {
      "ODDS_API_KEY": "...",
      "BASE_BANKROLL": 200.0,
      "UNIT_FRACTION": 0.01
    }

- Maintains bet_history.csv
- Fetches odds from The Odds API
- Builds value picks using a simple Kelly-based model
- Writes data.json with structure expected by the frontend:
    {
      "generated": "...",
      "picks": [...],
      "history": [...],
      "analytics": {
         "total_bets": ...,
         "wins": ...,
         "losses": ...,
         "pushes": ...,
         "roi": ...,
         "sport_roi": {...},
         "bankroll_history": [...]
      }
    }
"""

import csv
import json
import math
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Dict, Any

import requests

CONFIG_PATH = "config.json"
BET_HISTORY_PATH = "bet_history.csv"
DATA_JSON_PATH = "data.json"

# Supported sports
SPORTS = [
    "basketball_nba",
    "americanfootball_nfl",
    "americanfootball_ncaaf",
    "icehockey_nhl",
    "baseball_mlb",
    "soccer_epl",
    "mma_mixed_martial_arts",
]

MARKETS = ["h2h", "spreads", "totals"]
ODDS_API_BASE = "https://api.the-odds-api.com/v4/sports"
MAX_KELLY_FRACTION = 0.02  # Cap Kelly to 2% of bankroll


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(
            f"{CONFIG_PATH} not found. Create it with at least ODDS_API_KEY, "
            "BASE_BANKROLL, and UNIT_FRACTION."
        )
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if "ODDS_API_KEY" not in cfg or not cfg["ODDS_API_KEY"]:
        raise ValueError("ODDS_API_KEY missing from config.json")

    cfg.setdefault("BASE_BANKROLL", 200.0)
    cfg.setdefault("UNIT_FRACTION", 0.01)
    return cfg


def american_to_prob(odds: float) -> float:
    odds = float(odds)
    if odds < 0:
        return -odds / (-odds + 100)
    return 100 / (odds + 100)


def kelly_fraction(p: float, odds: float) -> float:
    """Basic Kelly formula with guardrails."""
    if odds < 0:
        b = 100.0 / abs(odds)
    else:
        b = odds / 100.0
    q = 1.0 - p
    k = (b * p - q) / b
    if k <= 0:
        return 0.0
    return min(k, MAX_KELLY_FRACTION)


def make_bet_id(sport: str, match: str, team: str, market: str, event_time: str) -> str:
    raw = f"{sport}_{match}_{team}_{market}_{event_time}"
    return "".join(c if c.isalnum() or c == "_" else "_" for c in raw)


@dataclass
class Pick:
    bet_id: str
    sport: str
    match: str
    team: str
    market: str
    price: float
    implied_prob: float
    model_prob: float
    ev: float
    recommended_fraction: float
    recommended_stake: float
    event_time: str


def fetch_odds_for_sport(api_key: str, sport: str) -> List[Dict[str, Any]]:
    url = f"{ODDS_API_BASE}/{sport}/odds"
    params = {
        "apiKey": api_key,
        "regions": "us",
        "markets": ",".join(MARKETS),
        "oddsFormat": "american",
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def build_picks_from_odds(odds_json: List[Dict[str, Any]], sport: str,
                          bankroll: float, unit_fraction: float) -> List[Pick]:
    picks: List[Pick] = []

    for game in odds_json:
        home = game.get("home_team", "Home")
        away = game.get("away_team", "Away")
        match = f"{away} @ {home}"
        event_time = game.get("commence_time", "")

        bookmakers = game.get("bookmakers") or []
        if not bookmakers:
            continue

        # Take the first bookmaker's markets for simplicity
        bm = bookmakers[0]
        markets = bm.get("markets") or []
        for m in markets:
            market_key = m.get("key")
            if market_key not in MARKETS:
                continue

            outcomes = m.get("outcomes") or []
            for o in outcomes:
                team = o.get("name")
                price = o.get("price")
                if team is None or price is None:
                    continue

                price = float(price)
                implied = american_to_prob(price)
                # Very simple model: slightly shade toward favorites
                model_prob = max(0.01, min(0.99, implied + 0.01))

                # Compute edge EV
                if price < 0:
                    b = 100.0 / abs(price)
                else:
                    b = price / 100.0
                ev = model_prob * b - (1.0 - model_prob)

                k = kelly_fraction(model_prob, price)
                k = min(k, unit_fraction)
                stake = round(bankroll * k, 2)

                if stake <= 0:
                    continue

                bet_id = make_bet_id(sport, match, team, market_key, event_time)

                picks.append(
                    Pick(
                        bet_id=bet_id,
                        sport=sport,
                        match=match,
                        team=team,
                        market=market_key,
                        price=price,
                        implied_prob=implied,
                        model_prob=model_prob,
                        ev=ev,
                        recommended_fraction=k,
                        recommended_stake=stake,
                        event_time=event_time,
                    )
                )

    return picks


def dedupe_picks(picks: List[Pick]) -> List[Pick]:
    """Keep only best EV pick per (sport, match, team, market)."""
    best: Dict[tuple, Pick] = {}
    for p in picks:
        key = (p.sport, p.match, p.team, p.market)
        if key not in best or p.ev > best[key].ev:
            best[key] = p
    return list(best.values())


def load_history() -> List[Dict[str, Any]]:
    if not os.path.exists(BET_HISTORY_PATH):
        return []

    rows: List[Dict[str, Any]] = []
    with open(BET_HISTORY_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def save_history(rows: List[Dict[str, Any]]) -> None:
    fieldnames = [
        "bet_id",
        "timestamp",
        "date",
        "sport",
        "match",
        "team",
        "market",
        "odds",
        "stake",
        "event_time",
        "status",
        "result",
        "profit",
        "bankroll_after",
    ]
    with open(BET_HISTORY_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            # Ensure all fields exist
            normalized = {fn: row.get(fn, "") for fn in fieldnames}
            writer.writerow(normalized)


def normalize_history_rows(rows: List[Dict[str, Any]], base_bankroll: float) -> List[Dict[str, Any]]:
    """Ensure all legacy rows have required fields and sane defaults."""
    out: List[Dict[str, Any]] = []
    running_bankroll = base_bankroll
    for row in rows:
        result = row.get("result", "PENDING")
        profit_str = row.get("profit", "")
        try:
            profit = float(profit_str)
        except (TypeError, ValueError):
            profit = 0.0

        running_bankroll += profit
        row["profit"] = f"{profit:.2f}"
        row.setdefault("status", "CLOSED" if result in ("WIN", "LOSS", "PUSH") else "OPEN")
        row["bankroll_after"] = f"{running_bankroll:.2f}"
        out.append(row)
    return out


def compute_analytics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(rows)
    wins = losses = pushes = 0
    total_stake = 0.0
    total_profit = 0.0

    sport_profit: Dict[str, float] = {}
    sport_stake: Dict[str, float] = {}
    bankroll_history: List[Dict[str, Any]] = []

    running_bankroll = 0.0
    for row in rows:
        result = row.get("result", "PENDING")
        try:
            stake = float(row.get("stake", 0.0))
        except (TypeError, ValueError):
            stake = 0.0
        try:
            profit = float(row.get("profit", 0.0))
        except (TypeError, ValueError):
            profit = 0.0
        sport = row.get("sport", "unknown")

        if result == "WIN":
            wins += 1
        elif result == "LOSS":
            losses += 1
        elif result == "PUSH":
            pushes += 1

        total_stake += stake
        total_profit += profit

        sport_profit[sport] = sport_profit.get(sport, 0.0) + profit
        sport_stake[sport] = sport_stake.get(sport, 0.0) + stake

        running_bankroll += profit
        bankroll_history.append(
            {
                "t": row.get("timestamp", ""),
                "bankroll": round(running_bankroll, 2),
            }
        )

    roi = (total_profit / total_stake) if total_stake > 0 else 0.0
    sport_roi = {
        sp: (sport_profit[sp] / sport_stake[sp]) if sport_stake[sp] > 0 else 0.0
        for sp in sport_profit
    }

    return {
        "total_bets": total,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "roi": roi,
        "sport_roi": sport_roi,
        "bankroll_history": bankroll_history,
    }


def export_data_json(picks: List[Pick], history_rows: List[Dict[str, Any]], analytics: Dict[str, Any]) -> None:
    data = {
        "generated": now_iso(),
        "picks": [asdict(p) for p in picks],
        "history": history_rows,
        "analytics": analytics,
    }
    with open(DATA_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def main() -> None:
    cfg = load_config()
    api_key = cfg["ODDS_API_KEY"]
    base_bankroll = float(cfg["BASE_BANKROLL"])
    unit_fraction = float(cfg["UNIT_FRACTION"])

    print("[INFO] SmartPicks backend starting…")

    # 1) Load & normalize history
    history_rows = load_history()
    history_rows = normalize_history_rows(history_rows, base_bankroll)

    # 2) Fetch odds and build picks for each sport
    all_picks: List[Pick] = []
    for sport in SPORTS:
        try:
            odds_json = fetch_odds_for_sport(api_key, sport)
            sport_picks = build_picks_from_odds(
                odds_json, sport, base_bankroll, unit_fraction
            )
            all_picks.extend(sport_picks)
        except Exception as e:
            print(f"[WARN] Failed fetching odds for {sport}: {e}")

    # 3) Dedupe picks
    all_picks = dedupe_picks(all_picks)

    # 4) Add any truly new picks into history as OPEN/PENDING
    now_date = datetime.now().strftime("%m/%d/%y")
    now_stamp = now_iso()

    # Determine last known bankroll
    if history_rows:
        try:
            last_bankroll = float(history_rows[-1].get("bankroll_after", base_bankroll))
        except (TypeError, ValueError):
            last_bankroll = base_bankroll
    else:
        last_bankroll = base_bankroll

    existing_ids = {row.get("bet_id") for row in history_rows}
    for p in all_picks:
        if p.bet_id in existing_ids:
            continue
        history_rows.append(
            {
                "bet_id": p.bet_id,
                "timestamp": now_stamp,
                "date": now_date,
                "sport": p.sport,
                "match": p.match,
                "team": p.team,
                "market": p.market,
                "odds": f"{p.price:.0f}",
                "stake": f"{p.recommended_stake:.2f}",
                "event_time": p.event_time,
                "status": "OPEN",
                "result": "PENDING",
                "profit": "0.00",
                "bankroll_after": f"{last_bankroll:.2f}",
            }
        )

    # 5) Save normalized history
    save_history(history_rows)

    # 6) Compute analytics
    analytics = compute_analytics(history_rows)

    # 7) Export data.json for frontend
    export_data_json(all_picks, history_rows, analytics)

    print("[INFO] SmartPicks backend finished successfully.")


if __name__ == "__main__":
    main()
