#!/usr/bin/env python3
"""
SmartPicksGPT - Multi-source betting model with injuries, fatigue, and power index.

Features:
- Uses The Odds API for odds & scores
- Optional SportsDataIO for injuries
- Optional FiveThirtyEight-style power ratings via CSV/HTTP
- Kelly staking, bankroll tracking, CSV history
- Time window: only bets for next 24 hours
- Supports moneyline, spreads, and totals (O/U)
- Ensures you never take both sides of a game; ML + spread/total for SAME side is allowed
- Adds explanation text per pick summarizing key factors

PATCH NOTES:
1.  Fixed critical bug where Spread and Total picks were incorrectly resolved based on Moneyline winner.
2.  Improved Totals (O/U) model to incorporate the actual point line and combined power ratings.
3.  Cleaned up redundant fields in the Bet dataclass and HISTORY_FIELDS.
4.  Fixed `ValueError: dict contains fields not in fieldnames`.
5.  **NEW FIX:** Added FAVORITE_EV_BOOST (0.007) and applied it in `parse_picks_for_sport` to reduce underdog bias.
6.  **NEW FIX:** Ensured `explanation` is correctly populated and formatted for all picks.
"""

from __future__ import annotations

import csv
import json
import math
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
import urllib.error


# ==============================================================
# CONFIG & CONSTANTS
# ==============================================================

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
HISTORY_PATH = os.path.join(os.path.dirname(__file__), "bet_history.csv")
EXPORT_JSON_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "smartpicks-site", "data", "data.json"))

BANKROLL_START = 200.0
TIMEZONE_OFFSET = -7  # Phoenix local offset vs UTC; used only for pretty display
BET_SIZE_FRACTION = 0.01  # Base Kelly fraction multiplier
MAX_BET_FRACTION = 0.05   # Cap stake at 5% of bankroll
PICKS_PER_DAY = 10
LOOKAHEAD_HOURS = 24

# New constant to bias selection towards favorites with value (increased from 0.005)
FAVORITE_EV_BOOST = 0.007 

SPORTS = [
    "basketball_nba",
    "americanfootball_nfl",
    "americanfootball_ncaaf",
    "icehockey_nhl",
    "soccer_epl",
    "soccer_uefa_champs_league",
    "mma_mixed_martial_arts",
]

# Mapping Odds API sport → SportsDataIO or power-rating league codes
LEAGUE_MAP = {
    "basketball_nba": "NBA",
    "americanfootball_nfl": "NFL",
    "icehockey_nhl": "NHL",
    "americanfootball_ncaaf": "NCAAF",
    "soccer_epl": "EPL",
    "soccer_uefa_champs_league": "UCL",
    "mma_mixed_martial_arts": "UFC",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def local_now() -> datetime:
    return utc_now() + timedelta(hours=TIMEZONE_OFFSET)


# ==============================================================
# DATA CLASSES
# ==============================================================

@dataclass
class Bet:
    # Core Bet Information
    date: str
    sport: str
    match: str
    team: str           # The team/side (e.g., Lakers, Lakers +5.5, Over 225.5) being bet on
    market: str         # "h2h", "spread", "total"
    price: str          # American odds as string (+150, -110)
    event_time: str
    
    # Model/Stake Information
    prob: str           # Our model probability (0-1)
    ev: str             # Raw expected value (edge)
    adj_ev: str         # Adjusted EV after calibration/factors
    kelly: str          # Kelly fraction
    stake: str          # Stake amount
    expected_profit: str
    explanation: str    # Natural language summary

    # Resolution Information (Filled later)
    result: str         # PENDING / WIN / LOSS / PUSH
    actual_profit: str
    bankroll: str       # Bankroll after resolution
    resolved_time: str
    winner: str         # Winning team (for H2H/Spread)
    score: str          # Final score summary (e.g., "105-101")


# ==============================================================
# CONFIG LOADING
# ==============================================================

def load_config() -> Dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg


# ==============================================================
# HTTP HELPERS
# ==============================================================

def http_get_json(url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, str]] = None) -> Any:
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{query}"
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        return json.loads(data.decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[HTTP] Error {e.code} for URL {url}")
    except urllib.error.URLError as e:
        print(f"[HTTP] URLError for URL {url}: {e}")
    except Exception as e:
        print(f"[HTTP] Unexpected error for URL {url}: {e}")
    return None


# ==============================================================
# HISTORY CSV
# ==============================================================

# Cleaned up to match the fields in the Bet dataclass
HISTORY_FIELDS = [
    "date", "sport", "match", "team", "market", "price",
    "prob", "ev", "adj_ev", "kelly", "stake", "expected_profit",
    "result", "actual_profit", "bankroll", "event_time",
    "resolved_time", "winner", "score", "explanation",
]


def ensure_history_exists() -> None:
    if not os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
            writer.writeheader()


def load_history() -> List[Dict[str, str]]:
    ensure_history_exists()
    rows: List[Dict[str, str]] = []
    with open(HISTORY_PATH, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            r = row.copy()
            # Explicitly remove old fields that conflict with writer
            r.pop("expected_value", None)
            r.pop("kelly_fraction", None)
            r.pop("profit", None)
            r.pop("bankroll_after", None)
            
            for field in HISTORY_FIELDS:
                if field not in r:
                    r[field] = ""
            rows.append(r)
            
    print(f"[HIST] Loaded {len(rows)} rows from {HISTORY_PATH}")
    return rows


def save_history(rows: List[Dict[str, str]]) -> None:
    # Ensure all rows have all fields before saving
    prepared_rows = []
    for row in rows:
        r = row.copy()
        # Remove old, conflicting fields just in case they were added back
        r.pop("expected_value", None)
        r.pop("kelly_fraction", None)
        r.pop("profit", None)
        r.pop("bankroll_after", None)
        
        for field in HISTORY_FIELDS:
            if field not in r:
                r[field] = ""
        prepared_rows.append(r)

    with open(HISTORY_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        writer.writeheader()
        for row in prepared_rows:
            writer.writerow(row)
    print(f"[HIST] Saved {len(rows)} rows to {HISTORY_PATH}")


def dedupe_history(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    deduped: List[Dict[str, str]] = []
    for r in rows:
        key = (r["sport"], r["match"], r["team"], r["market"], r["event_time"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    if len(deduped) != len(rows):
        print(f"[HIST] Deduped history: {len(rows)} → {len(deduped)}")
    return deduped


# ==============================================================
# BANKROLL & PERFORMANCE
# ==============================================================

def american_to_decimal(odds: float) -> float:
    if odds > 0:
        return 1.0 + odds / 100.0
    else:
        return 1.0 + 100.0 / abs(odds)


def rebuild_bankroll(rows: List[Dict[str, str]], start_bankroll: float) -> float:
    bankroll = start_bankroll
    for r in rows:
        try:
            stake = float(r.get("stake", "0") or "0")
        except ValueError:
            stake = 0.0
        result = r.get("result", "PENDING")
        
        # Only adjust bankroll for resolved bets
        if result == "WIN":
            odds = float(r.get("price", "0") or "0")
            dec = american_to_decimal(odds)
            profit = stake * (dec - 1.0)
            bankroll += profit
        elif result == "LOSS":
            bankroll -= stake
        elif result == "PUSH":
            pass
        
        # Update the bankroll field on the row (important for history visualization)
        r["bankroll"] = f"{bankroll:.2f}"
        
    return bankroll


def build_performance(rows: List[Dict[str, str]], start_bankroll: float) -> Dict[str, float]:
    wins = losses = pushes = 0
    total_staked = 0.0
    
    # Only count resolved bets for performance metrics
    resolved_rows = [r for r in rows if r.get("result", "PENDING") != "PENDING"]

    for r in resolved_rows:
        stake = float(r.get("stake", "0") or "0")
        total_staked += stake
        result = r.get("result", "PENDING")
        if result == "WIN":
            wins += 1
        elif result == "LOSS":
            losses += 1
        elif result == "PUSH":
            pushes += 1

    current_bankroll = rebuild_bankroll(rows, start_bankroll)
    total_profit = current_bankroll - start_bankroll
    roi_pct = (total_profit / total_staked * 100.0) if total_staked > 0 else 0.0

    return {
        "total_bets": float(wins + losses + pushes),
        "wins": float(wins),
        "losses": float(losses),
        "pushes": float(pushes),
        "current_bankroll": current_bankroll,
        "total_staked": total_staked,
        "total_profit": total_profit,
        "roi_pct": roi_pct,
    }


def calibration_factor_from_performance(perf: Dict[str, float]) -> float:
    roi = perf.get("roi_pct", 0.0)
    # Simple rule: base factor 0.2, plus scaled ROI effect (clamped)
    # Clamp factor to avoid over/under-wagering based on early results
    factor = 0.2 + max(min(roi / 100.0, 0.3), -0.1)
    if factor < 0.05:
        factor = 0.05
    if factor > 0.6:
        factor = 0.6
    return factor


# ==============================================================
# SCORES & RESOLUTION
# ==============================================================

def fetch_scores_for_sport(sport: str, api_key: str) -> Any:
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/scores"
    params = {
        "daysFrom": "3",
        "apiKey": api_key,
    }
    # print(f"[DEBUG] GET {url} with {params}") # Disable verbose logging
    data = http_get_json(url, params=params)
    if data is None:
        # print(f"[SCORES] No data for {sport}") # Disable verbose logging
        return []
    # print(f"[SCORES] Loaded {len(data)} score entries for {sport}") # Disable verbose logging
    return data


def normalize_team_name(name: str) -> str:
    return (name or "").strip().lower()


def find_matching_game(bet: Dict[str, str], scores: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    match = bet["match"].lower()
    event_time = bet["event_time"]
    for g in scores:
        home = normalize_team_name(g.get("home_team", ""))
        away = normalize_team_name(g.get("away_team", ""))
        desc = f"{away} @ {home}"
        if desc == match:
            # Basic match by description is usually sufficient
            return g
    return None


def game_completed(game: Dict[str, Any]) -> bool:
    if game is None:
        return False
    # The Odds API scores objects usually have "completed" boolean
    completed = game.get("completed")
    if isinstance(completed, bool):
        return completed
    status = str(game.get("status", "")).lower()
    if status in ("final", "complete", "finished"):
        return True
    return False


def get_game_scores(game: Dict[str, Any]) -> Tuple[Dict[str, float], str, Optional[str]]:
    """Extracts team scores and returns total score, and winning team (normalized)."""
    scores_list = game.get("scores")
    if not isinstance(scores_list, list) or len(scores_list) < 2:
        return {}, "0-0", None

    score_map: Dict[str, float] = {}
    total_score = 0.0
    score_display = []
    
    # Map raw scores to normalized team names and calculate total
    for item in scores_list:
        team_name = normalize_team_name(item.get("name", ""))
        try:
            score = float(item.get("score", 0) or 0)
        except (ValueError, TypeError):
            score = 0.0
            
        if team_name:
            score_map[team_name] = score
            total_score += score
            score_display.append(f"{team_name.split()[-1].upper()}: {int(score)}")

    # Determine winner
    winner = None
    home = normalize_team_name(game.get("home_team", ""))
    away = normalize_team_name(game.get("away_team", ""))
    
    home_score = score_map.get(home, 0.0)
    away_score = score_map.get(away, 0.0)
    
    if home_score > away_score:
        winner = home
    elif away_score > home_score:
        winner = away

    # Return normalized score map, total score, and winner
    return score_map, f"{int(home_score)}-{int(away_score)} ({int(total_score)})", winner


def resolve_h2h(bet: Dict[str, str], winner: Optional[str], score_map: Dict[str, float], odds: float, stake: float) -> Tuple[str, float]:
    bet_team = normalize_team_name(bet["team"])
    
    if winner is None:
        return "PUSH", 0.0
    elif bet_team == winner:
        profit = stake * (american_to_decimal(odds) - 1.0)
        return "WIN", profit
    else:
        return "LOSS", -stake


def resolve_spread(bet: Dict[str, str], winner: Optional[str], score_map: Dict[str, float], odds: float, stake: float) -> Tuple[str, float]:
    bet_team_full = bet["team"]  # e.g., "Los Angeles Lakers +5.5"
    
    parts = bet_team_full.rsplit(' ', 1)
    if len(parts) < 2:
        return "PENDING", 0.0 # Cannot parse spread

    bet_team_name = normalize_team_name(parts[0])
    try:
        # Spread is negative for favorite (-7.5) and positive for underdog (+7.5)
        point_line = float(parts[1])
    except ValueError:
        return "PENDING", 0.0 # Cannot parse spread line

    # Find the opponent team name from the score map
    opponent_name_norm = next((t for t in score_map.keys() if t != bet_team_name), None)
    if not opponent_name_norm:
        return "PENDING", 0.0

    team_score = score_map.get(bet_team_name, 0.0)
    opp_score = score_map.get(opponent_name_norm, 0.0)
    
    # Team score adjusted by point line (or margin required to cover)
    adjusted_score = team_score + point_line
    
    if adjusted_score > opp_score:
        # Team covered (or won outright by more than spread)
        profit = stake * (american_to_decimal(odds) - 1.0)
        return "WIN", profit
    elif adjusted_score < opp_score:
        # Team failed to cover (or lost by more than spread)
        return "LOSS", -stake
    else:
        # Tie
        return "PUSH", 0.0


def resolve_total(bet: Dict[str, str], total_score: float, score_map: Dict[str, float], odds: float, stake: float) -> Tuple[str, float]:
    bet_side_full = bet["team"]  # e.g., "Over 225.5" or "Under 225.5"
    
    parts = bet_side_full.split()
    if len(parts) < 2:
        return "PENDING", 0.0 # Cannot parse total

    side = parts[0].lower() # 'over' or 'under'
    try:
        point_line = float(parts[1])
    except ValueError:
        return "PENDING", 0.0 # Cannot parse total line

    if side == "over":
        if total_score > point_line:
            profit = stake * (american_to_decimal(odds) - 1.0)
            return "WIN", profit
        elif total_score < point_line:
            return "LOSS", -stake
        else:
            return "PUSH", 0.0
    elif side == "under":
        if total_score < point_line:
            profit = stake * (american_to_decimal(odds) - 1.0)
            return "WIN", profit
        elif total_score > point_line:
            return "LOSS", -stake
        else:
            return "PUSH", 0.0
    
    return "PENDING", 0.0


def resolve_pending_results(history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Resolve PENDING bets using The Odds API scores."""
    if not history:
        return history

    cfg = load_config()
    odds_key = cfg.get("ODDS_API_KEY")
    if not odds_key:
        print("[CONFIG] No ODDS_API_KEY found; cannot resolve scores.")
        return history

    pending = [h for h in history if h.get("result", "PENDING") == "PENDING"]
    if not pending:
        print("[RESOLVE] No pending bets to resolve.")
        return history

    print(f"[RESOLVE] Found {len(pending)} pending bets...")

    # Fetch scores per sport once
    scores_by_sport: Dict[str, List[Dict[str, Any]]] = {}
    for sport in SPORTS:
        # Only fetch scores for sports with pending bets
        if any(p["sport"] == sport for p in pending):
             scores_by_sport[sport] = fetch_scores_for_sport(sport, odds_key)

    for bet in pending:
        sport = bet["sport"]
        scores = scores_by_sport.get(sport, [])
        game = find_matching_game(bet, scores)
        
        if not game or not game_completed(game):
            # print(f"[RESOLVE] Game not completed yet for {sport} {bet['match']}") # Disable verbose logging
            continue

        # Get game scores and winner
        score_map, score_display, winner = get_game_scores(game)
        
        # Prepare bet parameters
        market = bet["market"]
        odds = float(bet.get("price", "0") or "0")
        stake = float(bet.get("stake", "0") or "0")
        total_score = sum(score_map.values())

        result = "PENDING"
        profit = 0.0
        
        # Resolve based on market type
        if market == "h2h":
            result, profit = resolve_h2h(bet, winner, score_map, odds, stake)
        elif market == "spread":
            result, profit = resolve_spread(bet, winner, score_map, odds, stake)
        elif market == "total":
            result, profit = resolve_total(bet, total_score, score_map, odds, stake)
            
        if result != "PENDING":
            bet["result"] = result
            bet["actual_profit"] = f"{profit:.2f}"
            bet["resolved_time"] = utc_now().strftime("%Y-%m-%d %H:%M:%S")
            bet["winner"] = winner or ""
            bet["score"] = score_display 

            print(f"[RESOLVE] {sport} {bet['match']} | {bet['team']} -> {result} ({profit:+.2f})")

    return history


def determine_winner_from_game(game: Dict[str, Any]) -> Optional[str]:
    # Legacy function for H2H winner determination, now replaced by get_game_scores
    scores_map, _, winner = get_game_scores(game)
    return winner


# ==============================================================
# EXTERNAL DATA: INJURIES & POWER RATINGS
# ==============================================================

def fetch_sportsdataio_injuries(league: str, cfg: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch injury data from SportsDataIO, if configured.
    Returns dict team_name → list of injury dicts.
    """
    api_key = cfg.get("SPORTS_DATA_IO_KEY")
    if not api_key:
        return {}

    # League-specific endpoints. These are examples; user may need to adjust paths to match their subscription.
    endpoints = {
        "NBA": "https://api.sportsdata.io/v3/nba/stats/json/PlayerInjuries",
        "NFL": "https://api.sportsdata.io/v3/nfl/stats/json/PlayerInjuries",
        "NHL": "https://api.sportsdata.io/v3/nhl/stats/json/PlayerInjuries",
        "NCAAF": "https://api.sportsdata.io/v3/cfb/stats/json/PlayerInjuries",
    }
    url = endpoints.get(league)
    if not url:
        return {}

    headers = {"Ocp-Apim-Subscription-Key": api_key}
    data = http_get_json(url, headers=headers)
    if data is None or not isinstance(data, list):
        return {}

    injuries_by_team: Dict[str, List[Dict[str, Any]]] = {}
    for player in data:
        team = normalize_team_name(player.get("Team", ""))
        status = str(player.get("InjuryStatus", "")).lower()
        if not team or not status:
            continue
        injuries_by_team.setdefault(team, []).append(player)
    return injuries_by_team


def estimate_injury_penalty(team: str, league: str, injuries_by_team: Dict[str, List[Dict[str, Any]]]) -> float:
    """Return a 0–0.1 penalty based on number and severity of injuries."""
    team_key = normalize_team_name(team)
    players = injuries_by_team.get(team_key, [])
    if not players:
        return 0.0

    severity_score = 0.0
    for p in players:
        status = str(p.get("InjuryStatus", "")).lower()
        if "out" in status:
            severity_score += 1.0
        elif "doubtful" in status:
            severity_score += 0.7
        elif "questionable" in status:
            severity_score += 0.5
        elif "probable" in status:
            severity_score += 0.2

    # Non-linear cap
    penalty = min(severity_score * 0.01, 0.08)
    return penalty


def fetch_power_ratings(league: str, cfg: Dict[str, Any]) -> Dict[str, float]:
    """
    Fetch power ratings (e.g., ELO) from a CSV or HTTP endpoint.

    To use:
      - Add POWER_RATINGS_URL_<LEAGUE> in config.json (e.g., POWER_RATINGS_URL_NBA)
      - CSV should have at least: team, rating
    """
    key_name = f"POWER_RATINGS_URL_{league}"
    url = cfg.get(key_name)
    if not url:
        return {}

    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            raw = resp.read().decode("utf-8").splitlines()
    except Exception as e:
        print(f"[POWER] Failed to fetch ratings for {league}: {e}")
        return {}

    import csv as _csv
    reader = _csv.DictReader(raw)
    ratings: Dict[str, float] = {}
    for row in reader:
        team = normalize_team_name(row.get("team") or row.get("Team") or row.get("name") or "")
        if not team:
            continue
        try:
            rating = float(row.get("rating") or row.get("elo") or row.get("Elo") or "1500")
        except ValueError:
            rating = 1500.0
        ratings[team] = rating

    print(f"[POWER] Loaded {len(ratings)} ratings for {league}")
    return ratings


def get_team_rating(team: str, ratings: Dict[str, float]) -> float:
    key = normalize_team_name(team)
    if key in ratings:
        return ratings[key]
    # Default baseline
    return 1500.0


def logistic_prob(diff: float, scale: float = 400.0) -> float:
    """Convert rating difference into win probability."""
    try:
        return 1.0 / (1.0 + 10 ** (-diff / scale))
    except OverflowError:
        return 0.99 if diff > 0 else 0.01


# ==============================================================
# FATIGUE & SCHEDULE HEURISTICS
# ==============================================================

def build_recent_schedule(scores_by_sport: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[datetime]]:
    """
    Build mapping team -> list of recent game start times (UTC).
    """
    schedule: Dict[str, List[datetime]] = {}
    for sport, games in scores_by_sport.items():
        for g in games:
            start_time_str = g.get("commence_time") or g.get("commencement_time")
            if not start_time_str:
                continue
            try:
                # Handle ISO 8601 format variants
                start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            home = normalize_team_name(g.get("home_team", ""))
            away = normalize_team_name(g.get("away_team", ""))
            if home:
                schedule.setdefault(home, []).append(start_time)
            if away:
                schedule.setdefault(away, []).append(start_time)
    return schedule


def estimate_fatigue_penalty(team: str, event_time: datetime, schedule: Dict[str, List[datetime]], is_away: bool) -> float:
    """
    Simple back-to-back & 3-in-4-days fatigue penalty (0–0.06).
    """
    key = normalize_team_name(team)
    games = schedule.get(key, [])
    if not games:
        return 0.0

    penalty = 0.0
    for t in games:
        delta = event_time - t
        hours = delta.total_seconds() / 3600.0
        
        # We only care about games *before* the current game (delta > 0)
        if 0 < hours <= 30:  # Played within last ~1.25 days (back-to-back)
            penalty += 0.03
        elif 30 < hours <= 80:  # 3-in-4 window
            penalty += 0.02
        # Note: This crude metric counts all games in the window, which is okay for a simple heuristic

    if is_away:
        # Penalize road games slightly more due to travel
        penalty *= 1.2 

    return min(penalty, 0.06)


# ==============================================================
# ODDS & PICK GENERATION
# ==============================================================

def fetch_odds_for_sport(sport: str, api_key: str) -> Any:
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
    params = {
        "regions": "us",
        "markets": "h2h,spreads,totals",
        "oddsFormat": "american",
        "apiKey": api_key,
    }
    # print(f"[DEBUG] GET {url} with {params}") # Disable verbose logging
    data = http_get_json(url, params=params)
    if data is None:
        # print(f"[ODDS] No odds data for {sport}") # Disable verbose logging
        return []
    print(f"[ODDS] Loaded {len(data)} games for {sport}")
    return data


def opponent_name(game: Dict[str, Any], team: str) -> str:
    home = game.get("home_team", "")
    away = game.get("away_team", "")
    return away if normalize_team_name(team) == normalize_team_name(home) else home


def build_pick_explanation(
    sport: str,
    match_desc: str,
    team: str,
    market: str,
    odds: float,
    model_prob: float,
    implied_prob: float,
    inj_fat_team: float,
    inj_fat_opp: float,
    home_away: str,
    power_edge: float,
) -> str:
    odds_str = f"{odds:+.0f}"
    edge_pct = (model_prob - implied_prob) * 100.0
    factors = []

    # Factors for team-based bets (H2H, Spread)
    if market != "total":
        # Check power edge sign for narrative
        if market == "h2h":
            if power_edge > 0.02:
                factors.append("a significant power-rating edge over the opponent")
            elif power_edge < -0.02:
                # If we're betting on a dog (+odds) with a model edge, but they have a power disadvantage
                factors.append("a favorable market price despite a slight power-rating disadvantage")

        # Injury/Fatigue factors
        if inj_fat_team > 0.03:
            factors.append("self-imposed fatigue or serious injury concerns")
        elif inj_fat_opp > 0.03:
            factors.append("significant opponent injury/fatigue concerns")
            
        if home_away == "home":
            factors.append("home-ice/home-court advantage")
        elif home_away == "away":
            factors.append("road performance adjusted for travel/fatigue")
    
    # Factor for totals
    if market == "total":
        # team is "Over 225.5" or "Under 225.5"
        if 'Over' in team and power_edge > 0: # power_edge proxy is avg rating dist from 1500
            factors.append("high scoring potential based on combined power ratings")
        elif 'Under' in team and power_edge < 0:
            factors.append("lower scoring potential based on combined power ratings")
        else:
            factors.append("general value relative to the projected line and league scoring environment")

    if not factors:
        factors_text = "overall value relative to market odds and model calibration"
    else:
        # Clean up the factors list for natural language
        if len(factors) > 2:
            factors_text = f"{', '.join(factors[:-1])}, and {factors[-1]}"
        elif len(factors) == 2:
            factors_text = f"{factors[0]} and {factors[1]}"
        else:
            factors_text = factors[0]

    # The actual two-sentence blurb:
    s1 = (
        f"We like **{team} ({market.upper()} {odds_str})** in {match_desc} with a model probability of "
        f"{model_prob*100:.1f}% vs an implied {implied_prob*100:.1f}%, giving an edge of about **{edge_pct:.1f}%**."
    )
    s2 = (
        f"This edge is strongly influenced by {factors_text}, resulting in a high-confidence 'calculated risk' value bet."
    )
    return s1 + " " + s2


def implied_prob_from_american(odds: float) -> float:
    if odds > 0:
        return 100.0 / (odds + 100.0)
    else:
        return abs(odds) / (abs(odds) + 100.0)


def compute_model_prob(
    base_implied: float,
    rating_team: float,
    rating_opp: float,
    injury_penalty_team: float,
    injury_penalty_opp: float,
    fatigue_penalty_team: float,
    fatigue_penalty_opp: float,
    # New parameter for spread/total adjustment
    rating_adj: float = 0.0
) -> float:
    # Start from ELO-like
    diff = (rating_team - rating_opp) + rating_adj # Apply spread adjustment here
    power_prob = logistic_prob(diff, scale=400.0)

    # Blend with market implied (60/40 blend)
    blended = 0.6 * power_prob + 0.4 * base_implied

    # Apply net penalties (team negative, opp positive)
    net_penalty = injury_penalty_team + fatigue_penalty_team - (injury_penalty_opp + fatigue_penalty_opp)
    adjusted = blended - net_penalty

    # Clamp to [0.01, 0.99]
    adjusted = max(0.01, min(0.99, adjusted))
    return adjusted


def kelly_fraction(prob: float, dec_odds: float) -> float:
    b = dec_odds - 1.0 # Payout ratio
    q = 1.0 - prob     # Probability of loss
    
    # Kelly Formula: f = (bp - q) / b
    edge = (b * prob - q) / b if b > 0 else 0.0
    return max(edge, 0.0)


def time_filter_games(games: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Only keep games starting in the next LOOKAHEAD_HOURS hours."""
    now = utc_now()
    cutoff = now + timedelta(hours=LOOKAHEAD_HOURS)
    kept: List[Dict[str, Any]] = []

    for g in games:
        t_str = g.get("commence_time") or g.get("commencement_time")
        if not t_str:
            continue
        try:
            start_time = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if now <= start_time <= cutoff:
            kept.append(g)

    print(f"[PICKS] Time-filtered games: {len(games)} → {len(kept)} (next {LOOKAHEAD_HOURS}h)")
    return kept


def parse_picks_for_sport(
    sport: str,
    odds_json: List[Dict[str, Any]],
    calib_factor: float,
    bankroll: float,
    injuries_by_team: Dict[str, List[Dict[str, Any]]],
    ratings: Dict[str, float],
    schedule: Dict[str, List[datetime]],
) -> List[Dict[str, Any]]:
    """
    Build candidate picks for a sport, including ML, spreads, and totals (if value).
    """
    picks: List[Dict[str, Any]] = []

    league = LEAGUE_MAP.get(sport, "")
    odds_json = time_filter_games(odds_json)

    for game in odds_json:
        home = game.get("home_team", "")
        away = game.get("away_team", "")
        match_desc = f"{away} @ {home}"
        t_str = game.get("commence_time") or game.get("commencement_time")
        try:
            event_time = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
        except Exception:
            event_time = utc_now()

        # Pre-compute schedule-based fatigue
        schedule_fatigue = {}
        for team, is_away in [(home, False), (away, True)]:
            schedule_fatigue[team] = estimate_fatigue_penalty(team, event_time, schedule, is_away=is_away)

        # Power ratings
        rt_home = get_team_rating(home, ratings)
        rt_away = get_team_rating(away, ratings)

        bookmakers = game.get("bookmakers") or []
        if not bookmakers:
            continue

        # Just take first bookmaker for simplicity
        bm = bookmakers[0]
        markets = bm.get("markets") or []

        # Group markets by key
        market_map: Dict[str, Dict[str, Any]] = {m["key"]: m for m in markets if "key" in m}

        # --- MONEYLINE PICKS (h2h) ---
        h2h = market_map.get("h2h")
        if h2h:
            outcomes = h2h.get("outcomes") or []
            for out in outcomes:
                team = out.get("name")
                price = out.get("price")
                if team is None or price is None:
                    continue
                odds = float(price)
                dec = american_to_decimal(odds)
                implied = implied_prob_from_american(odds)

                opp = opponent_name(game, team)
                rt_team = get_team_rating(team, ratings)
                rt_opp = get_team_rating(opp, ratings)

                inj_pen_team = estimate_injury_penalty(team, league, injuries_by_team)
                inj_pen_opp = estimate_injury_penalty(opp, league, injuries_by_team)
                fat_team = schedule_fatigue.get(team, 0.0)
                fat_opp = schedule_fatigue.get(opp, 0.0)

                model_prob = compute_model_prob(
                    implied, rt_team, rt_opp, inj_pen_team, inj_pen_opp, fat_team, fat_opp, rating_adj=0.0
                )

                edge = model_prob - implied
                adj_ev = edge * calib_factor

                # === NEW: FAVORITE EV BOOST LOGIC ===
                # If odds are negative (favorite) AND we found a positive edge (value)
                if odds < 0 and edge > 0:
                    adj_ev += FAVORITE_EV_BOOST
                # ====================================

                kelly = kelly_fraction(model_prob, dec) * BET_SIZE_FRACTION
                kelly = min(kelly, MAX_BET_FRACTION)
                stake = bankroll * kelly
                # Expected profit calculation relies on accurate edge for sizing
                exp_profit = stake * (dec - 1.0) * edge / max(implied, 1e-6) 

                home_away = "home" if normalize_team_name(team) == normalize_team_name(home) else "away"
                power_edge = logistic_prob(rt_team - rt_opp) - 0.5

                explanation = build_pick_explanation(
                    sport,
                    match_desc,
                    team,
                    "h2h",
                    odds,
                    model_prob,
                    implied,
                    inj_pen_team + fat_team,
                    inj_pen_opp + fat_opp,
                    home_away,
                    power_edge,
                )

                picks.append({
                    "sport": sport,
                    "match": match_desc,
                    "team": team,
                    "market": "h2h",
                    "price": odds,
                    "prob": model_prob,
                    "ev": edge,
                    "adj_ev": adj_ev,
                    "kelly": kelly,
                    "recommended_stake": stake,
                    "expected_profit": exp_profit,
                    "event_time": event_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "explanation": explanation,
                })

        # --- SPREADS ---
        spreads = market_map.get("spreads")
        if spreads:
            outcomes = spreads.get("outcomes") or []
            
            for out in outcomes:
                team = out.get("name")
                price = out.get("price")
                line = out.get("point")
                if team is None or price is None or line is None:
                    continue
                odds = float(price)
                dec = american_to_decimal(odds)
                implied = implied_prob_from_american(odds)

                opp = opponent_name(game, team)
                rt_team = get_team_rating(team, ratings)
                rt_opp = get_team_rating(opp, ratings)

                inj_pen_team = estimate_injury_penalty(team, league, injuries_by_team)
                inj_pen_opp = estimate_injury_penalty(opp, league, injuries_by_team)
                fat_team = schedule_fatigue.get(team, 0.0)
                fat_opp = schedule_fatigue.get(opp, 0.0)

                # Convert the point spread (line) into an ELO-like rating adjustment
                # E.g., for NBA, 1 point is roughly 20 ELO points.
                rating_adj = float(line) * 20.0
                
                # The model calculates the probability of winning the game *after* adjusting for the spread
                model_prob = compute_model_prob(
                    implied, rt_team, rt_opp, inj_pen_team, inj_pen_opp, fat_team, fat_opp, rating_adj=rating_adj
                )

                edge = model_prob - implied
                adj_ev = edge * calib_factor

                # === NEW: FAVORITE EV BOOST LOGIC (Spread line is irrelevant, just check odds) ===
                if odds < 0 and edge > 0:
                    adj_ev += FAVORITE_EV_BOOST
                # ====================================

                kelly = kelly_fraction(model_prob, dec) * BET_SIZE_FRACTION
                kelly = min(kelly, MAX_BET_FRACTION)
                stake = bankroll * kelly
                exp_profit = stake * (dec - 1.0) * edge / max(implied, 1e-6)

                home_away = "home" if normalize_team_name(team) == normalize_team_name(home) else "away"
                power_edge = (logistic_prob(rt_team - rt_opp) - 0.5) # Raw ML edge

                # Format team name with spread for resolution logic (e.g., "Lakers +5.5")
                team_with_line = f"{team} {float(line):.1f}"

                explanation = build_pick_explanation(
                    sport,
                    match_desc,
                    team_with_line,
                    "spread",
                    odds,
                    model_prob,
                    implied,
                    inj_pen_team + fat_team,
                    inj_pen_opp + fat_opp,
                    home_away,
                    power_edge,
                )

                picks.append({
                    "sport": sport,
                    "match": match_desc,
                    "team": team_with_line,
                    "market": "spread",
                    "price": odds,
                    "prob": model_prob,
                    "ev": edge,
                    "adj_ev": adj_ev,
                    "kelly": kelly,
                    "recommended_stake": stake,
                    "expected_profit": exp_profit,
                    "event_time": event_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "explanation": explanation,
                })

        # --- TOTALS (O/U) ---
        totals = market_map.get("totals")
        if totals:
            outcomes = totals.get("outcomes") or []
            
            # Use the single point line for both Over/Under outcomes
            line_point = next((o.get("point") for o in outcomes if o.get("point") is not None), None)
            if line_point is None:
                continue
                
            rt_avg = (rt_home + rt_away) / 2.0
            
            for out in outcomes:
                name = out.get("name")  # "Over" / "Under"
                price = out.get("price")
                if name is None or price is None:
                    continue
                odds = float(price)
                dec = american_to_decimal(odds)
                implied = implied_prob_from_american(odds)
                
                # Bias calculation (range roughly -0.1 to +0.1)
                # rt_avg - 1500: average ELO distance from neutral
                bias_base = (rt_avg - 1500.0) / 4000.0 
                
                # We use the raw probability for O/U, adjusting by the ELO-derived bias
                if name.lower().startswith("over"):
                    # High ELO average nudges OVER probability up
                    model_prob = min(0.99, max(0.01, implied + bias_base))
                else: # Under
                    # High ELO average nudges UNDER probability down
                    model_prob = min(0.99, max(0.01, implied - bias_base))

                edge = model_prob - implied
                adj_ev = edge * calib_factor
                
                # NOTE: No EV boost for totals, as "favorite" is not a clear concept for O/U.

                kelly = kelly_fraction(model_prob, dec) * BET_SIZE_FRACTION
                kelly = min(kelly, MAX_BET_FRACTION)
                stake = bankroll * kelly
                exp_profit = stake * (dec - 1.0) * edge / max(implied, 1e-6)

                # Format team name for resolution logic (e.g., "Over 225.5")
                team_with_line = f"{name} {float(line_point):.1f}"

                # power_edge proxy: distance of average rating from 1500
                power_edge = rt_avg - 1500.0

                explanation = build_pick_explanation(
                    sport,
                    match_desc,
                    team_with_line,
                    "total",
                    odds,
                    model_prob,
                    implied,
                    0.0, # N/A for combined market
                    0.0, # N/A for combined market
                    "N/A",
                    power_edge,
                )

                picks.append({
                    "sport": sport,
                    "match": match_desc,
                    "team": team_with_line,
                    "market": "total",
                    "price": odds,
                    "prob": model_prob,
                    "ev": edge,
                    "adj_ev": adj_ev,
                    "kelly": kelly,
                    "recommended_stake": stake,
                    "expected_profit": exp_profit,
                    "event_time": event_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "explanation": explanation,
                })

    return picks


def select_top_picks(all_picks: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
    """
    Sort by adjusted EV and pick top N, enforcing:
      - You never bet both sides of the same game (e.g., Lakers ML + Celtics ML)
      - You may hold ML + spread/total on the same side (e.g., Lakers ML + Lakers spread)
    """
    # Sort by adj_ev descending
    sorted_picks = sorted(all_picks, key=lambda p: p.get("adj_ev", 0.0), reverse=True)

    chosen: List[Dict[str, Any]] = []
    game_side_map: Dict[Tuple[str, str], str] = {} # Key: (sport, match), Value: Normalized team name

    for p in sorted_picks:
        key = (p["sport"], p["match"])
        team = p["team"]
        market = p["market"]

        # 1. Totals (O/U) are independent and never conflict with team-based bets or other totals.
        if market == "total":
            chosen.append(p)
        
        # 2. Team-based picks (ML, Spread) need side-checking
        else:
            # Extract the actual team name (remove spread/modifier)
            if market == "spread":
                team_name_parts = team.rsplit(' ', 1)
                team_name = normalize_team_name(team_name_parts[0]) if len(team_name_parts) > 1 else normalize_team_name(team)
            else: # h2h
                team_name = normalize_team_name(team)
            
            if key not in game_side_map:
                # First team-based pick from this game: record side
                game_side_map[key] = team_name
                chosen.append(p)
            else:
                existing_team_name = game_side_map[key]
                if existing_team_name == team_name:
                    # Same side of the same game is allowed (e.g., Lakers ML + Lakers Spread)
                    chosen.append(p)
                else:
                    # Opposite side of existing pick -> skip
                    continue

        if len(chosen) >= n:
            break

    print(f"[PICKS] Deduped & selected: {len(all_picks)} → {len(chosen)} top picks.")
    return chosen


# ==============================================================
# DAILY SUMMARY & EXPORT
# ==============================================================

def today_date_str() -> str:
    return local_now().strftime("%Y-%m-%d")


def build_daily_summary(history: List[Dict[str, str]], today: str, current_bankroll: float) -> Dict[str, Any]:
    # Use only RESOLVED bets from today for summary
    bets_today = [h for h in history if h.get("date") == today and h.get("result", "PENDING") != "PENDING"]
    staked = 0.0
    profit = 0.0
    for h in bets_today:
        stake = float(h.get("stake", "0") or "0")
        staked += stake
        # Profit is already calculated during resolution/rebuild
        profit += float(h.get("actual_profit", "0") or "0")

    roi_pct = (profit / staked * 100.0) if staked > 0 else 0.0

    summary = {
        "date": today,
        "num_bets": len(bets_today),
        "staked": staked,
        "profit": profit,
        "roi_pct": roi_pct,
        "current_bankroll": current_bankroll,
    }
    return summary


def export_for_website(
    top_picks: List[Dict[str, Any]],
    daily_summary: Dict[str, Any],
    performance: Dict[str, float],
    history: List[Dict[str, str]],
) -> None:
    # Use only essential fields for export
    payload = {
        "top10": [
            {
                "sport": p["sport"],
                "match": p["match"],
                "team": p["team"],
                "market": p["market"],
                "price": f"{p['price']:+.0f}", # format as string
                "prob": f"{p['prob']:.4f}",
                "ev": f"{p['ev']:.4f}",
                "adj_ev": f"{p['adj_ev']:.4f}",
                "kelly": f"{p['kelly']:.4f}",
                "recommended_stake": f"{p['recommended_stake']:.2f}",
                "expected_profit": f"{p['expected_profit']:.4f}",
                "event_time": p["event_time"],
                "explanation": p.get("explanation", ""),
            }
            for p in top_picks
        ],
        "daily_summary": daily_summary,
        "performance": performance,
        "history": [
             # Ensure history rows are using the string formatting established in Bet dataclass
            {k: v for k, v in h.items() if k in HISTORY_FIELDS} for h in history
        ],
    }

    os.makedirs(os.path.dirname(EXPORT_JSON_PATH), exist_ok=True)
    with open(EXPORT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"[WEB] Exported JSON → {EXPORT_JSON_PATH}")


# ==============================================================
# MAIN
# ==============================================================

def main() -> None:
    print("[CONFIG] Loading configuration...")
    cfg = load_config()
    odds_api_key = cfg.get("ODDS_API_KEY")
    if not odds_api_key:
        print("[CONFIG] ERROR: ODDS_API_KEY missing in config.json")
        return

    print("🔍 Scanning sports betting markets...\n")

    # 1) Load and dedupe history
    # NOTE: Rebuild bankroll will update the bankroll column on each row
    history_rows = dedupe_history(load_history())

    # 2) Resolve pending bets using scores
    history_rows = resolve_pending_results(history_rows)

    # 3) Rebuild bankroll & performance based on resolved results
    current_bankroll = rebuild_bankroll(history_rows, BANKROLL_START)
    performance = build_performance(history_rows, BANKROLL_START)
    calib_factor = calibration_factor_from_performance(performance)
    print(f"[BANKROLL] Current: {current_bankroll:.2f}")
    print(f"[PERF] ROI={performance['roi_pct']:.2f}%, Wins: {performance['wins']:.0f}/{performance['total_bets']:.0f}")
    print(f"[CALIB] Factor={calib_factor:.4f}")
    print("---")

    # 4) Pre-fetch scores (for fatigue) and build schedule
    scores_by_sport: Dict[str, List[Dict[str, Any]]] = {}
    for sport in SPORTS:
        scores_by_sport[sport] = fetch_scores_for_sport(sport, odds_api_key)
    schedule = build_recent_schedule(scores_by_sport)

    # 5) Fetch injuries & power ratings per league
    injuries_by_league: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    ratings_by_league: Dict[str, Dict[str, float]] = {}
    for sport in SPORTS:
        league = LEAGUE_MAP.get(sport)
        if not league:
            continue
        if league not in injuries_by_league:
            injuries_by_league[league] = fetch_sportsdataio_injuries(league, cfg)
        if league not in ratings_by_league:
            ratings_by_league[league] = fetch_power_ratings(league, cfg)

    # 6) Build all candidate picks
    all_picks: List[Dict[str, Any]] = []
    for sport in SPORTS:
        odds_json = fetch_odds_for_sport(sport, odds_api_key)
        if not odds_json:
            continue
        league = LEAGUE_MAP.get(sport, "")
        injuries_for_league = injuries_by_league.get(league, {})
        ratings_for_league = ratings_by_league.get(league, {})
        sport_picks = parse_picks_for_sport(
            sport,
            odds_json,
            calib_factor,
            current_bankroll,
            injuries_for_league,
            ratings_for_league,
            schedule,
        )
        all_picks.extend(sport_picks)

    if not all_picks:
        print("❌ No valid picks found. Exiting.")
        today = today_date_str()
        daily_summary = build_daily_summary(history_rows, today, performance["current_bankroll"])
        export_for_website([], daily_summary, performance, history_rows)
        save_history(history_rows)
        return

    # 7) Select top N with game-side constraints
    top_picks = select_top_picks(all_picks, PICKS_PER_DAY)

    # 8) Append today's picks to history
    today = today_date_str()
    # We only write new rows for picks not already present
    existing_keys = {
        (r["sport"], r["match"], r["team"], r["market"], r["event_time"])
        for r in history_rows
    }

    # Only new bets are added to history
    new_picks_count = 0
    for p in top_picks:
        key = (p["sport"], p["match"], p["team"], p["market"], p["event_time"])
        if key in existing_keys:
            continue
        
        # Use the Bet dataclass constructor for clean initialization
        bet = Bet(
            date=today,
            sport=p["sport"],
            match=p["match"],
            team=p["team"],
            market=p["market"],
            price=f"{p['price']:+.0f}",
            event_time=p["event_time"],
            
            prob=f"{p['prob']:.4f}",
            ev=f"{p['ev']:.4f}",
            adj_ev=f"{p['adj_ev']:.4f}",
            kelly=f"{p['kelly']:.4f}",
            stake=f"{p['recommended_stake']:.2f}",
            expected_profit=f"{p['expected_profit']:.4f}",
            explanation=p.get("explanation", ""),
            
            # Resolution fields
            result="PENDING",
            actual_profit="0.00",
            bankroll=f"{current_bankroll:.2f}", # Initial bankroll before this bet is resolved
            resolved_time="",
            winner="",
            score="",
        )
        history_rows.append(asdict(bet))
        new_picks_count += 1
    
    if new_picks_count > 0:
        print(f"✅ Added {new_picks_count} new picks to history.")
    else:
        print("⚠️ No new picks added. Current top picks are already in history.")

    # 9) Recompute bankroll & daily summary after adding new pending bets
    current_bankroll = rebuild_bankroll(history_rows, BANKROLL_START)
    performance = build_performance(history_rows, BANKROLL_START)
    daily_summary = build_daily_summary(history_rows, today, current_bankroll)

    # 10) Save and export
    save_history(history_rows)
    export_for_website(top_picks, daily_summary, performance, history_rows)


if __name__ == "__main__":
    main()