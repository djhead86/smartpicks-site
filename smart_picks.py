#!/usr/bin/env python3
"""
SmartPicks v0.1.9

- Looser, more practical filters (no strict EV gate).
- Supports NBA, NFL, NHL, EPL.
- Grades finished bets using /scores.
- Writes data/data.json for the dashboard.
- Auto-commits and pushes changes to git (Option A).
"""

import csv
import json
import math
import sys
import time
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# ---------------------------------------------------------------------------
# Configuration / constants
# ---------------------------------------------------------------------------

VERSION = "0.1.9"

# Where this script lives
ROOT_DIR = Path(__file__).resolve().parent

# Files
BET_HISTORY_FILE = ROOT_DIR / "bet_history.csv"
DATA_DIR = ROOT_DIR / "data"
DATA_FILE = DATA_DIR / "data.json"

# Timezone: Phoenix (MST, no DST)
TIMEZONE_OFFSET_HOURS = -7

# The Odds API sports to scan
SPORT_KEYS = [
    "basketball_nba",
    "americanfootball_nfl",
    "icehockey_nhl",
    "soccer_epl",
]

# Markets we care about
MARKETS = ["h2h", "spreads", "totals"]

# Pick limits
MAX_TOTAL_PICKS = 12
MAX_PICKS_PER_SPORT = 4

# Odds sanity limits
MIN_AMERICAN = -600   # avoid insane mega-favorites
MAX_AMERICAN = 400    # avoid ridiculous longshots

# CSV schema
CSV_HEADERS = [
    "timestamp",
    "sport",
    "event",
    "market",
    "team",
    "line",
    "odds",
    "bet_amount",
    "status",
    "result",
    "pnl",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(msg, flush=True)


def load_config() -> Dict[str, Any]:
    """
    Try a few common config filenames/locations so we work with your current setup.
    Expected keys (at minimum):
      - ODDS_API_KEY
      - BASE_BANKROLL
      - UNIT_FRACTION
    """
    candidates = [
        ROOT_DIR / "config.json",
        ROOT_DIR / "confg.json",
        ROOT_DIR.parent / "config.json",
        ROOT_DIR.parent / "confg.json",
    ]

    cfg: Optional[Dict[str, Any]] = None
    for p in candidates:
        if p.exists():
            try:
                cfg = json.loads(p.read_text())
                log(f"[CONFIG] Loaded: {p}")
                break
            except Exception as e:
                log(f"[WARN] Failed to load {p}: {e}")

    if not cfg:
        raise RuntimeError(
            "No config.json / confg.json found. "
            "Please create one with at least ODDS_API_KEY, BASE_BANKROLL, UNIT_FRACTION."
        )

    required = ["ODDS_API_KEY", "BASE_BANKROLL", "UNIT_FRACTION"]
    for key in required:
        if key not in cfg:
            raise RuntimeError(f"Missing required config key: {key}")

    return cfg

def event_already_bet(event_name: str, bet_history: List[Dict], current_candidates: List[Dict]) -> bool:
    """Returns True if this event already exists in past or current bets."""
    
    # Check historical bets
    for row in bet_history:
        if row.get("event") == event_name:
            return True

    # Check bets being built in this run
    for bet in current_candidates:
        if bet.get("event") == event_name:
            return True

    return False

def american_to_implied_prob(odds: int) -> float:
    """Convert American odds to implied probability (no vig removed)."""
    if odds == 0:
        return 0.5
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return -odds / (-odds + 100.0)


def profit_from_american(odds: int, stake: float) -> float:
    """Net profit (excluding stake) from American odds and stake."""
    if odds > 0:
        return stake * (odds / 100.0)
    return stake * (100.0 / -odds)


def parse_event_teams(event: str) -> Tuple[str, str]:
    """
    Event format is assumed "Away Team @ Home Team".
    """
    parts = event.split("@")
    if len(parts) != 2:
        return event.strip(), ""
    return parts[0].strip(), parts[1].strip()


def parse_iso_to_local(iso_str: str) -> str:
    """
    Convert The Odds API commence_time (ISO, UTC) to MST string.
    """
    if not iso_str:
        return ""
    # Strip Z if present
    iso_str = iso_str.replace("Z", "")
    try:
        dt_utc = datetime.fromisoformat(iso_str)
    except Exception:
        dt_utc = datetime.utcnow()
    dt_local = dt_utc + timedelta(hours=TIMEZONE_OFFSET_HOURS)
    return dt_local.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CandidateBet:
    sport: str
    event: str
    market: str           # "h2h" | "spreads" | "totals"
    team: str             # team name OR "over"/"under"
    line: float           # spread or total line; 0 for h2h
    odds: int             # American odds
    game_time: str        # local time string
    score: float          # internal scoring metric [0, 1]
    win_probability: float  # rough estimate (for UI only)


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def fetch_odds_for_sport(api_key: str, sport_key: str) -> List[Dict[str, Any]]:
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": "us",
        "markets": ",".join(MARKETS),
        "oddsFormat": "american",
    }
    log(f"[ODDS] GET {url}")
    resp = requests.get(url, params=params, timeout=15)
    if not resp.ok:
        log(f"[ODDS] Error {resp.status_code} for {sport_key}: {resp.text}")
        return []
    try:
        return resp.json()
    except Exception as e:
        log(f"[ODDS] Failed to parse JSON for {sport_key}: {e}")
        return []


def fetch_scores_for_sport(api_key: str, sport_key: str, days_from: int = 3) -> List[Dict[str, Any]]:
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/scores"
    params = {
        "apiKey": api_key,
        "daysFrom": str(days_from),
    }
    log(f"[SCORES] GET {url}")
    resp = requests.get(url, params=params, timeout=15)
    if not resp.ok:
        log(f"[SCORES] Error {resp.status_code} for {sport_key}: {resp.text}")
        return []
    try:
        return resp.json()
    except Exception as e:
        log(f"[SCORES] Failed to parse scores JSON for {sport_key}: {e}")
        return []


# ---------------------------------------------------------------------------
# Build candidate bets
# ---------------------------------------------------------------------------

def normalize_market_outcomes(game: Dict[str, Any], sport: str) -> List[CandidateBet]:
    """
    For a single game, collect best prices per (market, team/label, line).
    Returns a rough list of candidate bets BEFORE filtering/scoring.
    """
    away = game.get("away_team", "Away")
    home = game.get("home_team", "Home")
    event = f"{away} @ {home}"
    commence_time = game.get("commence_time", "")
    game_time = parse_iso_to_local(commence_time)

    best_by_key: Dict[Tuple[str, str, float], Dict[str, Any]] = {}

    bookmakers = game.get("bookmakers", [])
    for book in bookmakers:
        for market in book.get("markets", []):
            mkey = market.get("key")
            if mkey not in MARKETS:
                continue
            for out in market.get("outcomes", []):
                price = out.get("price")
                if price is None:
                    continue
                try:
                    odds = int(price)
                except Exception:
                    # Some books may return odds as string; try conversion
                    try:
                        odds = int(float(price))
                    except Exception:
                        continue

                # Filter out insane odds
                if odds < MIN_AMERICAN or odds > MAX_AMERICAN:
                    continue

                name = out.get("name", "")
                if mkey == "h2h":
                    team = name
                    line = 0.0
                elif mkey == "spreads":
                    team = name
                    line = float(out.get("point", 0.0))
                elif mkey == "totals":
                    team = name.lower()  # "Over" / "Under" -> "over"/"under"
                    line = float(out.get("point", 0.0))
                else:
                    continue

                key = (mkey, team, line)
                existing = best_by_key.get(key)
                # For favorites (negative odds), the "best" payout is the least negative (closest to zero).
                # For dogs (positive odds), best is the highest positive.
                if existing is None:
                    best_by_key[key] = {
                        "sport": sport,
                        "event": event,
                        "market": mkey,
                        "team": team,
                        "line": line,
                        "odds": odds,
                        "game_time": game_time,
                    }
                else:
                    prev_odds = existing["odds"]
                    if (odds < 0 and odds > prev_odds) or (odds > 0 and odds > prev_odds):
                        best_by_key[key] = {
                            "sport": sport,
                            "event": event,
                            "market": mkey,
                            "team": team,
                            "line": line,
                            "odds": odds,
                            "game_time": game_time,
                        }

    candidates: List[CandidateBet] = []
    now = datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET_HOURS)

    for (_, _, _), bet in best_by_key.items():
        # Simple time-based weight: nearer games get a slight boost
        try:
            gt = datetime.strptime(bet["game_time"], "%Y-%m-%d %H:%M:%S")
            hours_to_game = max((gt - now).total_seconds() / 3600.0, 0.0)
        except Exception:
            hours_to_game = 24.0

        time_weight = 1.0 / (1.0 + hours_to_game / 24.0)  # 0..1-ish

        odds = bet["odds"]
        p_implicit = american_to_implied_prob(odds)

        if bet["market"] == "h2h":
            # Prefer reasonably priced favorites or short dogs.
            if odds < 0:
                # Targets around -200 for favorites
                target = -200
                span = 200.0
            else:
                # Targets around +150 for dogs
                target = 150
                span = 200.0
            score_odds = max(0.0, 1.0 - abs(odds - target) / span)
            base_score = 0.6 * score_odds + 0.4 * time_weight
        elif bet["market"] in ("spreads", "totals"):
            # Prefer lines around -110-ish.
            target = -110
            span = 60.0
            score_odds = max(0.0, 1.0 - abs(abs(odds) - abs(target)) / span)
            base_score = 0.5 * score_odds + 0.5 * time_weight
        else:
            base_score = 0.3 * time_weight

        # Heuristic: win_probability is just a smoothed blend of implied prob + score
        win_prob = min(0.98, max(0.50, (p_implicit * 0.7 + base_score * 0.3)))

        candidates.append(
            CandidateBet(
                sport=bet["sport"],
                event=bet["event"],
                market=bet["market"],
                team=bet["team"],
                line=float(bet["line"]),
                odds=odds,
                game_time=bet["game_time"],
                score=round(base_score, 4),
                win_probability=round(win_prob, 4),
            )
        )

    return candidates


def build_candidates_from_api(api_key: str) -> List[CandidateBet]:
    all_candidates: List[CandidateBet] = []
    for sport in SPORT_KEYS:
        games = fetch_odds_for_sport(api_key, sport)
        if not games:
            continue
        for game in games:
            cands = normalize_market_outcomes(game, sport)
            all_candidates.extend(cands)
    return all_candidates


# ---------------------------------------------------------------------------
# CSV: load, resolve, write
# ---------------------------------------------------------------------------

def load_bet_history() -> List[Dict[str, Any]]:
    if not BET_HISTORY_FILE.exists():
        log(f"[HIST] No bet_history.csv found at {BET_HISTORY_FILE}, starting fresh.")
        return []

    rows: List[Dict[str, Any]] = []
    with BET_HISTORY_FILE.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Ensure all headers exist
            for h in CSV_HEADERS:
                row.setdefault(h, "")
            rows.append(row)
    log(f"[HIST] Loaded {len(rows)} rows from {BET_HISTORY_FILE}")
    return rows


def write_bet_history(rows: List[Dict[str, Any]]) -> None:
    with BET_HISTORY_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({h: row.get(h, "") for h in CSV_HEADERS})
    log(f"[HIST] Wrote {len(rows)} rows to {BET_HISTORY_FILE}")


def build_scores_index(api_key: str) -> Dict[str, Dict[str, Any]]:
    """
    Fetch scores for each sport and index by (away, home) pair.
    Returns:
      scores_index[sport][(away_team, home_team)] = game_json
    """
    index: Dict[str, Dict[Tuple[str, str], Dict[str, Any]]] = {}
    for sport in SPORT_KEYS:
        games = fetch_scores_for_sport(api_key, sport, days_from=5)
        game_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for g in games:
            away = g.get("away_team", "")
            home = g.get("home_team", "")
            key = (away, home)
            game_map[key] = g
        index[sport] = game_map
    return index

def resolve_open_bets(rows: List[Dict[str, Any]], api_key: str) -> None:
    """
    Mutates rows in-place, grading any resolvable open bets against final scores.
    """
    # Collect open bets
    open_rows = [r for r in rows if r.get("status", "").lower() == "open"]
    if not open_rows:
        log("[RESOLVE] No open bets to grade.")
        return

    log(f"[RESOLVE] Found {len(open_rows)} open bets; fetching scores...")
    scores_index = build_scores_index(api_key)

    # Main grading loop
    for row in rows:
        if row.get("status", "").lower() != "open":
            continue

        sport = row.get("sport", "")
        event = row.get("event", "")
        market = row.get("market", "")
        team = row.get("team", "")

        # Safe parsing
        try:
            line = float(row.get("line", "0") or 0.0)
        except:
            line = 0.0

        try:
            odds = int(float(row.get("odds", "0") or 0))
        except:
            odds = 0

        try:
            stake = float(row.get("bet_amount", "0") or 0.0)
        except:
            stake = 0.0

        # Scores missing for this sport
        if sport not in scores_index:
            continue

        # Parse teams from "Away @ Home"
        away_team, home_team = parse_event_teams(event)

        game_map = scores_index.get(sport, {})
        game = game_map.get((away_team, home_team))

        # Sometimes API flips home/away
        if not game:
            game = game_map.get((home_team, away_team))
            if not game:
                continue

        # -----------------------------
        # Only grade if game is finished
        # -----------------------------
        status_str = str(game.get("status", "")).lower()
        completed_flag = bool(game.get("completed", False))

        if not completed_flag and status_str not in (
            "final", "finished", "complete", "completed", "full time", "ft"
        ):
            continue

        # Pull scores
        scores_list = game.get("scores", [])
        team_scores = {s["name"]: int(s["score"]) for s in scores_list if "name" in s and "score" in s}

        if away_team not in team_scores or home_team not in team_scores:
            continue

        away_score = team_scores[away_team]
        home_score = team_scores[home_team]

        result = ""
        pnl = 0.0

        # -----------------------------
        # Market grading logic
        # -----------------------------

        # Moneyline
        if market == "h2h":
            if team == home_team:
                my_score, opp_score = home_score, away_score
            elif team == away_team:
                my_score, opp_score = away_score, home_score
            else:
                continue

            if my_score > opp_score:
                result = "won"
                pnl = profit_from_american(odds, stake)
            elif my_score < opp_score:
                result = "lost"
                pnl = -stake
            else:
                result = "push"

        # Spread
        elif market == "spreads":
            if team == home_team:
                my_score, opp_score = home_score, away_score
            elif team == away_team:
                my_score, opp_score = away_score, home_score
            else:
                continue

            margin = my_score - opp_score
            adjusted = margin + line

            if adjusted > 0:
                result = "won"
                pnl = profit_from_american(odds, stake)
            elif adjusted < 0:
                result = "lost"
                pnl = -stake
            else:
                result = "push"

        # Totals
        elif market == "totals":
            total_points = home_score + away_score

            if team.lower() == "over":
                if total_points > line:
                    result = "won"
                    pnl = profit_from_american(odds, stake)
                elif total_points < line:
                    result = "lost"
                    pnl = -stake
                else:
                    result = "push"

            elif team.lower() == "under":
                if total_points < line:
                    result = "won"
                    pnl = profit_from_american(odds, stake)
                elif total_points > line:
                    result = "lost"
                    pnl = -stake
                else:
                    result = "push"
            else:
                continue

        # -----------------------------
        # Apply result if graded
        # -----------------------------
        if result:
            row["status"] = "closed"
            row["result"] = result
            row["pnl"] = f"{pnl:.2f}"

    log("[RESOLVE] Finished grading open bets.")




# ---------------------------------------------------------------------------
# Stats + streaks + JSON
# ---------------------------------------------------------------------------


def compute_stats(
    rows: List[Dict[str, Any]],
    base_bankroll: float,
) -> Tuple[
    Dict[str, Any],            # stats_dict
    float,                     # bankroll
    Dict[str, int],            # streak_dict
    List[Dict[str, Any]],      # bankroll_history
    Dict[str, Dict[str, float]]  # market_roi
]:
    """
    Compute overall stats, bankroll, streaks, bankroll history, and ROI by market.

    Returns:
      stats_dict:
        {
          "total_bets": int,
          "win_pct": float,   # percent 0–100
          "roi": float,       # percent 0–100
          "by_sport": {
            "basketball_nba": {"bets": int, "win_pct": float, "roi": float},
            ...
          }
        }

      bankroll: base_bankroll + cumulative pnl of all closed bets.

      streak_dict:
        { "current": int, "best": int }

      bankroll_history:
        [
          { "time": "YYYY-MM-DD HH:MM:SS", "bankroll": float },
          ...
        ]

      market_roi:
        {
          "h2h":   {"bets": int, "wins": int, "losses": int, "pushes": int,
                    "stake": float, "pnl": float, "roi": float},
          "spreads": { ... },
          "totals": { ... },
          ...
        }
    """
    total_bets = 0
    wins = 0
    losses = 0
    pushes = 0
    total_staked = 0.0
    total_pnl = 0.0

    by_sport: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "bets": 0,
        "win_pct": 0.0,
        "roi": 0.0,
    })
    sport_staked: Dict[str, float] = defaultdict(float)
    sport_pnl: Dict[str, float] = defaultdict(float)
    sport_wins: Dict[str, int] = defaultdict(int)
    sport_losses: Dict[str, int] = defaultdict(int)

    # For bankroll history & streaks, only use closed (graded) bets
    def parse_ts(ts_str: str) -> datetime:
        for fmt in ("%m/%d/%y %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(ts_str, fmt)
            except Exception:
                continue
        return datetime.utcnow()

    closed = [
        r
        for r in rows
        if r.get("status", "").lower() != "open"
        and r.get("result", "")
    ]
    closed_sorted = sorted(closed, key=lambda r: parse_ts(r.get("timestamp", "")))

    # Bankroll history
    bankroll_history: List[Dict[str, Any]] = []
    running_bankroll = base_bankroll

    # Market-level aggregates
    market_agg: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "bets": 0,
        "wins": 0,
        "losses": 0,
        "pushes": 0,
        "stake": 0.0,
        "pnl": 0.0,
    })

    current_streak = 0
    best_streak = 0

    for r in closed_sorted:
        sport = r.get("sport", "").strip()
        market = r.get("market", "").strip()
        result = r.get("result", "").lower()

        try:
            stake = float(r.get("bet_amount", "0") or 0.0)
        except Exception:
            stake = 0.0
        try:
            pnl = float(r.get("pnl", "0") or 0.0)
        except Exception:
            pnl = 0.0

        total_bets += 1
        total_staked += stake
        total_pnl += pnl

        # Sport-level aggregation
        if sport:
            info = by_sport[sport]
            info["bets"] += 1
            sport_staked[sport] += stake
            sport_pnl[sport] += pnl

        # Market-level aggregation
        if market:
            m = market_agg[market]
            m["bets"] += 1
            m["stake"] += stake
            m["pnl"] += pnl

        # Result-level accounting
        if result == "won":
            wins += 1
            if sport:
                sport_wins[sport] += 1
            if market:
                market_agg[market]["wins"] += 1
            current_streak += 1
            best_streak = max(best_streak, current_streak)
        elif result == "lost":
            losses += 1
            if sport:
                sport_losses[sport] += 1
            if market:
                market_agg[market]["losses"] += 1
            current_streak = 0
        elif result == "push":
            pushes += 1
            if market:
                market_agg[market]["pushes"] += 1
            # Push does not break streak
        else:
            # Unknown result, ignore for W/L but still included in bankroll
            pass

        # Bankroll progression
        ts = parse_ts(r.get("timestamp", ""))
        running_bankroll += pnl
        bankroll_history.append({
            "time": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "bankroll": running_bankroll,
        })

    # Overall win rate and ROI
    win_pct = (wins / (wins + losses) * 100.0) if (wins + losses) > 0 else 0.0
    roi = (total_pnl / total_staked * 100.0) if total_staked > 0 else 0.0

    # Per-sport ROI and win%
    for sport, info in by_sport.items():
        w = sport_wins[sport]
        l = sport_losses[sport]
        staked = sport_staked[sport]
        pnl_s = sport_pnl[sport]

        info["win_pct"] = (w / (w + l) * 100.0) if (w + l) > 0 else 0.0
        info["roi"] = (pnl_s / staked * 100.0) if staked > 0 else 0.0

    bankroll = running_bankroll

    stats_dict: Dict[str, Any] = {
        "total_bets": total_bets,
        "win_pct": win_pct,
        "roi": roi,
        "by_sport": dict(by_sport),
    }
    streak_dict: Dict[str, int] = {
        "current": current_streak,
        "best": best_streak,
    }

    # Finalize market ROI view
    market_roi: Dict[str, Dict[str, float]] = {}
    for market, agg in market_agg.items():
        stake = float(agg["stake"] or 0.0)
        pnl_val = float(agg["pnl"] or 0.0)
        roi_m = (pnl_val / stake * 100.0) if stake > 0 else 0.0
        market_roi[market] = {
            "bets": int(agg["bets"]),
            "wins": int(agg["wins"]),
            "losses": int(agg["losses"]),
            "pushes": int(agg["pushes"]),
            "stake": stake,
            "pnl": pnl_val,
            "roi": roi_m,
        }

    return stats_dict, bankroll, streak_dict, bankroll_history, market_roi


def select_top_picks(candidates: List[CandidateBet]) -> List[CandidateBet]:
    """
    Select up to MAX_TOTAL_PICKS, with a soft cap per sport.
    """
    candidates_sorted = sorted(candidates, key=lambda c: c.score, reverse=True)
    per_sport_count: Dict[str, int] = defaultdict(int)
    selected: List[CandidateBet] = []

    for cand in candidates_sorted:
        if per_sport_count[cand.sport] >= MAX_PICKS_PER_SPORT:
            continue
        selected.append(cand)
        per_sport_count[cand.sport] += 1
        if len(selected) >= MAX_TOTAL_PICKS:
            break

    return selected

def update_data_json(
    rows: List[Dict[str, Any]],
    todays_picks: List[CandidateBet],
    base_bankroll: float,
    new_picks_generated: bool,
) -> None:
    """
    Build the dashboard payload and write data/data.json.

    Adds:
      - bankroll (current)
      - stats (overall + by_sport)
      - streak (current/best)
      - bankroll_history (for charts)
      - market_roi (ROI by market)
      - open_bets
      - todays_picks (with model score + win_probability)
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    stats, bankroll, streak, bankroll_history, market_roi = compute_stats(
        rows,
        base_bankroll,
    )

    open_bets = [r for r in rows if r.get("status", "").lower() == "open"]

    todays_picks_json = [
        {
            "sport": c.sport,
            "event": c.event,
            "market": c.market,
            "team": c.team,
            "line": c.line,
            "odds": c.odds,
            "score": c.score,
            "win_probability": c.win_probability,
            "game_time": c.game_time,
        }
        for c in todays_picks
    ]

    payload = {
        "bankroll": bankroll,
        "last_updated": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "open_bets": open_bets,
        "todays_picks": todays_picks_json,
        "new_picks_generated": bool(new_picks_generated),
        "stats": stats,
        "streak": streak,
        "bankroll_history": bankroll_history,
        "market_roi": market_roi,
    }

    DATA_FILE.write_text(json.dumps(payload, indent=2))
    log(f"[DATA] Wrote dashboard JSON to {DATA_FILE}")




# ---------------------------------------------------------------------------
# New bet creation
# ---------------------------------------------------------------------------

def build_existing_open_bet_keys(rows: List[Dict[str, Any]]) -> set:
    keys = set()
    for r in rows:
        if r.get("status", "").lower() != "open":
            continue
        key = (
            r.get("sport", ""),
            r.get("event", ""),
            r.get("market", ""),
            r.get("team", ""),
            str(r.get("line", "")),
        )
        keys.add(key)
    return keys


def append_new_bets(
    rows: List[Dict[str, Any]],
    picks: List[CandidateBet],
    unit_amount: float,
) -> int:
    """
    Append picks to bet_history, enforcing an event-level lock so we never
    create multiple open bets for the same game. Also avoids exact duplicates
    by key for extra safety.
    Returns number of new bets added.
    """
    # Build a set of existing open-bet keys (sport, event, market, team, line)
    existing_keys = build_existing_open_bet_keys(rows)

    # Build a set of events that already have at least one OPEN bet.
    # Once a bet is open for an event, we will not add any further bets
    # for that event until it is resolved.
    existing_open_events = {
        r.get("event", "")
        for r in rows
        if r.get("status", "").lower() == "open" and r.get("event", "")
    }

    now_str = datetime.now().strftime("%m/%d/%y %H:%M")

    added = 0
    for c in picks:
        # Strict event-level deduplication: skip if this event already has an open bet
        if c.event in existing_open_events:
            log(f"[DEDUP] Skipping event already locked: {c.event}")
            continue

        key = (c.sport, c.event, c.market, c.team, str(c.line))
        if key in existing_keys:
            # Already have this exact bet open; skip
            continue

        row = {
            "timestamp": now_str,
            "sport": c.sport,
            "event": c.event,
            "market": c.market,
            "team": c.team,
            "line": f"{c.line}",
            "odds": f"{c.odds}",
            "bet_amount": f"{unit_amount:.2f}",
            "status": "open",
            "result": "",
            "pnl": "",
        }
        rows.append(row)
        existing_keys.add(key)
        existing_open_events.add(c.event)
        added += 1

    if added > 0:
        log(f"[NEW] Added {added} new bets to bet_history.")
    else:
        log("[NEW] No new bets added (all picks already open or deduplicated).")

    return added



# ---------------------------------------------------------------------------
# Git auto-push (Option A)
# ---------------------------------------------------------------------------

def auto_git_commit_and_push() -> None:
    """
    Option A: After a successful run, automatically git add/commit/push.
    This assumes the script is in a git repo with a configured remote.
    """
    try:
        # Quick check: are we in a git repo?
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            log("[GIT] Not a git repository, skipping auto-push.")
            return

        # Stage files
        files_to_add = []
        if BET_HISTORY_FILE.exists():
            files_to_add.append(str(BET_HISTORY_FILE))
        if DATA_FILE.exists():
            files_to_add.append(str(DATA_FILE))

        if not files_to_add:
            log("[GIT] Nothing to add, skipping auto-push.")
            return

        subprocess.run(
            ["git", "add"] + files_to_add,
            cwd=ROOT_DIR,
            check=False,
        )

        msg = f"SmartPicks auto-update v{VERSION} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        commit = subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
        )

        if commit.returncode != 0:
            # Most common: "nothing to commit"
            log("[GIT] Commit skipped or failed:")
            if commit.stdout.strip():
                log(commit.stdout.strip())
            if commit.stderr.strip():
                log(commit.stderr.strip())
            return

        log("[GIT] Commit created, pushing...")
        push = subprocess.run(
            ["git", "push"],
            cwd=ROOT_DIR,
        )
        if push.returncode == 0:
            log("[GIT] Push successful.")
        else:
            log("[GIT] Push failed.")

    except FileNotFoundError:
        log("[GIT] git command not found, skipping auto-push.")
    except Exception as e:
        log(f"[GIT] Auto-push error: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: List[str]) -> None:
    log(f"🔍 SmartPicks v{VERSION} - scanning markets...")

    cfg = load_config()
    api_key: str = cfg["ODDS_API_KEY"]
    base_bankroll: float = float(cfg.get("BASE_BANKROLL", 200.0))
    unit_fraction: float = float(cfg.get("UNIT_FRACTION", 0.01))
    unit_amount: float = round(base_bankroll * unit_fraction, 2)

    rows = load_bet_history()

    # 1) Resolve existing open bets
    resolve_open_bets(rows, api_key)

    # 2) Build candidate picks from The-Odds API
    candidates = build_candidates_from_api(api_key)
    log(f"[CAND] Built {len(candidates)} raw candidates.")

    # 3) Select top picks
    top_picks = select_top_picks(candidates)
    log(f"[PICKS] Selected {len(top_picks)} top picks.")

    # 4) Append to bet_history (avoid duplicates)
    added = append_new_bets(rows, top_picks, unit_amount)

    # 5) Write out bet_history.csv
    write_bet_history(rows)

    # 6) Update data/data.json for the dashboard
    update_data_json(
        rows=rows,
        todays_picks=top_picks,
        base_bankroll=base_bankroll,
        new_picks_generated=(added > 0),
    )

    log("✅ SmartPicks run complete.")


if __name__ == "__main__":
    main(sys.argv[1:])
    auto_git_commit_and_push()
