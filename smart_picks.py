"""
SmartPicks v4 Backend Engine

Features:
- Multi-sport odds retrieval from The Odds API (v4)
- EV and Smart Score calculation with sport-specific thresholds
- Risk management (event-level deduplication, max open bets)
- Automatic grading of finished events using Odds API scores
- Historical tracking via placed_bets.json and bet_history.csv
- Frontend outputs: data.json and scores.json
"""

from __future__ import annotations

import csv
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# =============================================================================
# PATHS & CONSTANTS
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent

CONFIG_PATH = BASE_DIR / "config.json"
PLACED_BETS_PATH = BASE_DIR / "placed_bets.json"
PERFORMANCE_PATH = BASE_DIR / "performance.json"
BET_HISTORY_PATH = BASE_DIR / "bet_history.csv"
DATA_JSON_PATH = BASE_DIR / "data.json"
SCORES_JSON_PATH = BASE_DIR / "scores.json"

ODDS_API_BASE = "https://api.the-odds-api.com/v4/sports"
SCORES_DAYS_FROM = 1
HTTP_TIMEOUT = 10
MAX_OPEN_BETS = 50

# Smart Score thresholds and pretty names per sport
SPORTS: Dict[str, Dict[str, Any]] = {
    "basketball_nba": {
        "pretty": "NBA",
        "smart_score_threshold": 1.2,
        "weight": 1.0,
    },
    "americanfootball_nfl": {
        "pretty": "NFL",
        "smart_score_threshold": 1.0,
        "weight": 1.0,
    },
    "icehockey_nhl": {
        "pretty": "NHL",
        "smart_score_threshold": 1.0,
        "weight": 1.0,
    },
    "soccer_epl": {
        "pretty": "EPL",
        "smart_score_threshold": 1.0,
        "weight": 1.0,
    },
    # UFC / MMA – moneyline only rule (no Smart Score threshold)
    "mma_mixed_martial_arts": {
        "pretty": "UFC",
        "smart_score_threshold": 0.0,
        "weight": 1.0,
        "ufc_moneyline_only": True,
    },
}

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# =============================================================================
# UTILS
# =============================================================================


def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing config.json at {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    # Basic sanity defaults
    cfg.setdefault("BASE_BANKROLL", 200.0)
    cfg.setdefault("UNIT_FRACTION", 0.01)
    return cfg


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error("Failed to read %s: %s", path, e)
        return default


def write_json(path: Path, payload: Any) -> None:
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        logging.error("Failed to write %s: %s", path, e)


def load_placed_bets() -> List[Dict[str, Any]]:
    data = read_json(PLACED_BETS_PATH, default=[])
    if not isinstance(data, list):
        logging.warning("placed_bets.json malformed; resetting to empty list.")
        return []
    return data


def save_placed_bets(bets: List[Dict[str, Any]]) -> None:
    write_json(PLACED_BETS_PATH, bets)


def load_performance_metrics() -> Dict[str, Any]:
    return read_json(PERFORMANCE_PATH, default={
        "overall": {
            "total_bets": 0,
            "wins": 0,
            "losses": 0,
            "pushes": 0,
            "win_rate": 0.0,
            "roi": 0.0,
            "total_wagered": 0.0,
            "total_profit": 0.0,
        },
        "by_sport": {},
        "by_bet_type": {},
    })


def save_performance_metrics(perf: Dict[str, Any]) -> None:
    write_json(PERFORMANCE_PATH, perf)


def ensure_bet_history_exists() -> None:
    if BET_HISTORY_PATH.exists():
        return
    with BET_HISTORY_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp",
            "sport_key",
            "sport",
            "event_id",
            "matchup",
            "pick_type",
            "pick",
            "odds",
            "stake",
            "status",
            "result",
            "profit",
        ])


def append_bets_to_history(bets: List[Dict[str, Any]]) -> None:
    ensure_bet_history_exists()
    with BET_HISTORY_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for b in bets:
            writer.writerow([
                b.get("created_at") or datetime.utcnow().isoformat(),
                b.get("sport_key", ""),
                b.get("sport", ""),
                b.get("event_id", ""),
                b.get("matchup", ""),
                b.get("pick_type", ""),
                b.get("pick", ""),
                b.get("odds", ""),
                b.get("stake", ""),
                b.get("status", ""),
                b.get("result", ""),
                b.get("profit", ""),
            ])


def parse_datetime(dt_str: str) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        # Odds API times are ISO8601 with Z
        if dt_str.endswith("Z"):
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# =============================================================================
# ODDS API HELPERS
# =============================================================================


def _http_get(url: str, params: Dict[str, Any]) -> Optional[Any]:
    try:
        resp = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        if resp.status_code != 200:
            logging.error("HTTP %s for %s: %s", resp.status_code, url, resp.text)
            return None
        return resp.json()
    except Exception as e:
        logging.error("HTTP request failed for %s: %s", url, e)
        return None


def fetch_odds_for_sport(sport_key: str, api_key: str) -> List[Dict[str, Any]]:
    url = f"{ODDS_API_BASE}/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": "us",
        "markets": "h2h,spreads,totals",
        "oddsFormat": "american",
    }
    data = _http_get(url, params)
    if data is None:
        return []
    if not isinstance(data, list):
        logging.error("Unexpected odds payload for %s", sport_key)
        return []
    return data


def fetch_scores_for_sport(sport_key: str, api_key: str, days_from: int = SCORES_DAYS_FROM) -> List[Dict[str, Any]]:
    url = f"{ODDS_API_BASE}/{sport_key}/scores"
    params = {
        "apiKey": api_key,
        "daysFrom": max(1, days_from),
    }
    data = _http_get(url, params)
    if data is None:
        return []
    if not isinstance(data, list):
        logging.error("Unexpected scores payload for %s", sport_key)
        return []
    return data


# =============================================================================
# EV & SMART SCORE
# =============================================================================


def american_to_probability(odds: int) -> float:
    """Convert American odds to implied probability."""
    try:
        o = int(odds)
    except Exception:
        return 0.0
    if o > 0:
        return 100.0 / (o + 100.0)
    else:
        return (-o) / ((-o) + 100.0)


def compute_ev_metrics(prices: List[int]) -> Tuple[float, float, float, int]:
    """
    Given a list of American prices for the same outcome across books,
    return (fair_prob, market_prob, ev, market_price).

    EV here is scaled (fair_prob - market_prob) * 100 to give intuitive values.
    """
    clean = [int(p) for p in prices if p is not None]
    if not clean:
        return 0.0, 0.0, 0.0, 0

    probs = [american_to_probability(p) for p in clean]
    if not probs:
        return 0.0, 0.0, 0.0, 0.0

    fair_prob = sum(probs) / len(probs)

    # Choose the "best" bookmaker price (most favorable to the bettor)
    positives = [p for p in clean if p > 0]
    negatives = [p for p in clean if p < 0]

    if positives:
        # Higher positive odds are better
        market_price = max(positives)
    elif negatives:
        # Less negative is better
        market_price = max(negatives)
    else:
        market_price = clean[0]

    market_prob = american_to_probability(market_price)
    ev = (fair_prob - market_prob) * 100.0  # scaled

    return fair_prob, market_prob, ev, market_price


def compute_smart_score(
    ev: float,
    fair_prob: float,
    market_prob: float,
    num_books: int,
    sport_key: str,
) -> float:
    """
    Smart Score blends:
    - EV (edge)
    - gap between fair and market probability
    - number of books (market sharpness / consensus)
    - sport weighting
    """
    if num_books <= 0:
        num_books = 1

    edge = max(ev, 0.0)
    prob_gap = max(fair_prob - market_prob, 0.0) * 100.0  # percentage points
    book_factor = 1.0 + min(num_books, 8) / 8.0  # 1.0–2.0 range
    sport_weight = SPORTS.get(sport_key, {}).get("weight", 1.0)

    raw_score = edge * (1.0 + prob_gap / 50.0) * book_factor * sport_weight
    return round(raw_score, 3)


# =============================================================================
# RISK & EVENT DEDUP
# =============================================================================


def is_duplicate_event(new_bet: Dict[str, Any], placed_bets: List[Dict[str, Any]]) -> bool:
    """
    Consider event duplicates if same sport_key, event_id, pick_type, and pick.
    """
    skey = new_bet.get("sport_key")
    eid = new_bet.get("event_id")
    mkt = new_bet.get("pick_type")
    pick = new_bet.get("pick")

    for b in placed_bets:
        if (
            b.get("sport_key") == skey
            and b.get("event_id") == eid
            and b.get("pick_type") == mkt
            and b.get("pick") == pick
            and b.get("status") in ("open", "pending")
        ):
            return True
    return False


def count_open_bets(placed_bets: List[Dict[str, Any]]) -> int:
    return sum(1 for b in placed_bets if b.get("status") in ("open", "pending"))


def dynamic_stake(base_stake: float, ev: float, smart_score: float) -> float:
    """
    Simple dynamic stake sizing:
    - Scale stake between 0.5x and 3x base based on Smart Score & EV.
    """
    edge_factor = max(ev, 0.0) / 50.0  # EV scaled
    score_factor = max(smart_score, 0.0) / 20.0
    multiplier = 1.0 + edge_factor + score_factor
    multiplier = max(0.5, min(multiplier, 3.0))
    return round(base_stake * multiplier, 2)


# =============================================================================
# ODDS PROCESSING → CANDIDATE BETS
# =============================================================================


def process_sport_odds(
    sport_key: str,
    odds_events: List[Dict[str, Any]],
    base_stake: float,
) -> List[Dict[str, Any]]:
    sport_cfg = SPORTS.get(sport_key, {})
    pretty = sport_cfg.get("pretty", sport_key)
    threshold = sport_cfg.get("smart_score_threshold", 0.0)
    ufc_moneyline_only = sport_cfg.get("ufc_moneyline_only", False)

    candidates: List[Dict[str, Any]] = []

    for event in odds_events:
        event_id = event.get("id")
        home_team = event.get("home_team", "Home")
        away_team = event.get("away_team", "Away")
        matchup = f"{away_team} @ {home_team}"
        commence_time = event.get("commence_time", "")

        bookmakers = event.get("bookmakers") or []
        if not bookmakers:
            continue

        # Collect outcome prices across all bookmakers for H2H market (and optionally others)
        # For simplicity and grading alignment, focus on h2h only.
        aggregated_markets: Dict[str, Dict[str, List[int]]] = {}

        for bm in bookmakers:
            for mkt in bm.get("markets") or []:
                mkt_key = mkt.get("key")  # "h2h", "spreads", "totals"
                if not mkt_key:
                    continue

                if ufc_moneyline_only and mkt_key != "h2h":
                    continue

                if mkt_key not in ("h2h",):
                    # You can extend to spreads/totals later; grading currently supports h2h.
                    continue

                outcomes = mkt.get("outcomes") or []
                for o in outcomes:
                    name = o.get("name")
                    price = o.get("price")
                    if name is None or price is None:
                        continue

                    aggregated_markets.setdefault(mkt_key, {}).setdefault(name, []).append(int(price))

        if not aggregated_markets:
            continue

        for mkt_key, outcome_prices in aggregated_markets.items():
            for outcome_name, prices in outcome_prices.items():
                fair_prob, market_prob, ev, market_price = compute_ev_metrics(prices)
                if market_price == 0:
                    continue

                smart_score = compute_smart_score(ev, fair_prob, market_prob, len(prices), sport_key)

                # For UFC we only require it's h2h; no minimum Smart Score filter.
                if not (ufc_moneyline_only and mkt_key == "h2h"):
                    if smart_score < threshold:
                        continue

                stake = dynamic_stake(base_stake, ev, smart_score)

                candidates.append({
                    "sport_key": sport_key,
                    "sport": pretty,
                    "event_id": event_id,
                    "commence_time": commence_time,
                    "home_team": home_team,
                    "away_team": away_team,
                    "matchup": matchup,
                    "pick_type": mkt_key,
                    "pick": outcome_name,
                    "odds": int(market_price),
                    "fair_prob": round(fair_prob, 6),
                    "market_prob": round(market_prob, 6),
                    "ev": round(ev, 3),
                    "smart_score": smart_score,
                    "stake": stake,
                    "status": "pending",
                    "result": None,
                    "profit": None,
                    "created_at": now_utc().isoformat(),
                    "source": "auto",
                })

    return candidates


# =============================================================================
# GRADING ENGINE (USING SCORES)
# =============================================================================


def extract_final_scores(score_event: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    scores = score_event.get("scores")
    if not isinstance(scores, list) or not scores:
        return None

    home_team = score_event.get("home_team")
    away_team = score_event.get("away_team")

    home_score = None
    away_score = None

    for s in scores:
        name = s.get("name")
        try:
            val = int(s.get("score", 0))
        except Exception:
            continue

        if name == home_team:
            home_score = val
        elif name == away_team:
            away_score = val

    if home_score is None or away_score is None:
        return None

    return home_score, away_score


def grade_bets(
    placed_bets: List[Dict[str, Any]],
    scores_by_sport: Dict[str, List[Dict[str, Any]]],
) -> None:
    """
    In-place grading of bets using Odds API scores.
    Only h2h bets are graded currently.
    """
    # Build reverse sport lookup by pretty name for legacy bets
    pretty_to_key = {cfg["pretty"]: key for key, cfg in SPORTS.items()}

    for bet in placed_bets:
        status = bet.get("status", "pending")
        if status in ("win", "loss", "push"):
            continue  # already graded

        pick_type = bet.get("pick_type")
        if pick_type != "h2h":
            continue  # grading implemented only for moneyline

        sport_key = bet.get("sport_key")
        if not sport_key:
            sport_pretty = bet.get("sport")
            sport_key = pretty_to_key.get(sport_pretty, "")

        if not sport_key:
            continue

        events = scores_by_sport.get(sport_key, [])
        if not events:
            continue

        event_id = bet.get("event_id")
        home_team = bet.get("home_team")
        away_team = bet.get("away_team")
        found = None

        # 1) Try by ID
        if event_id:
            for ev in events:
                if ev.get("id") == event_id:
                    found = ev
                    break

        # 2) Fallback to team names
        if found is None:
            for ev in events:
                if (
                    ev.get("home_team") == home_team
                    and ev.get("away_team") == away_team
                ):
                    found = ev
                    break

        if found is None:
            continue

        if not found.get("completed"):
            # Game not finished yet
            continue

        scores = extract_final_scores(found)
        if scores is None:
            continue

        home_score, away_score = scores
        pick = bet.get("pick")
        result_str = f"{away_team} {away_score} @ {home_team} {home_score}"

        # Determine winner
        if home_score > away_score:
            winner = home_team
        elif away_score > home_score:
            winner = away_team
        else:
            winner = None  # draw / push

        odds = int(bet.get("odds", 0))
        stake = float(bet.get("stake", 0.0))

        if winner is None:
            profit = 0.0
            new_status = "push"
        elif pick == winner:
            # win
            if odds > 0:
                profit = stake * (odds / 100.0)
            else:
                profit = stake * (100.0 / abs(odds))
            new_status = "win"
        else:
            profit = -stake
            new_status = "loss"

        bet["status"] = new_status
        bet["result"] = result_str
        bet["profit"] = round(profit, 2)


# =============================================================================
# PERFORMANCE METRICS
# =============================================================================


def aggregate_metrics(bets: List[Dict[str, Any]]) -> Dict[str, Any]:
    wins = losses = pushes = 0
    total_profit = 0.0
    total_wagered = 0.0

    for b in bets:
        status = b.get("status")
        stake = float(b.get("stake", 0.0))
        profit = float(b.get("profit") or 0.0)

        if status in ("win", "loss", "push"):
            total_wagered += stake

        if status == "win":
            wins += 1
        elif status == "loss":
            losses += 1
        elif status == "push":
            pushes += 1

        total_profit += profit

    total_bets = wins + losses + pushes
    win_rate = wins / total_bets if total_bets > 0 else 0.0
    roi = total_profit / total_wagered if total_wagered > 0 else 0.0

    return {
        "total_bets": total_bets,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "win_rate": round(win_rate * 100.0, 2),
        "roi": round(roi * 100.0, 2),
        "total_wagered": round(total_wagered, 2),
        "total_profit": round(total_profit, 2),
    }


def build_performance(bets: List[Dict[str, Any]]) -> Dict[str, Any]:
    overall = aggregate_metrics(bets)

    # By sport (pretty)
    by_sport: Dict[str, Any] = {}
    for skey, cfg in SPORTS.items():
        pretty = cfg["pretty"]
        sport_bets = [b for b in bets if b.get("sport") == pretty]
        if sport_bets:
            by_sport[pretty] = aggregate_metrics(sport_bets)

    # By bet type (pick_type)
    by_bet_type: Dict[str, Any] = {}
    bet_types = set(b.get("pick_type") for b in bets if b.get("pick_type"))
    for bt in bet_types:
        type_bets = [b for b in bets if b.get("pick_type") == bt]
        by_bet_type[bt] = aggregate_metrics(type_bets)

    return {
        "overall": overall,
        "by_sport": by_sport,
        "by_bet_type": by_bet_type,
    }


# =============================================================================
# FRONTEND JSON BUILDERS
# =============================================================================


def update_open_pending_statuses(bets: List[Dict[str, Any]]) -> None:
    """
    Normalize 'pending' vs 'open' based on commence_time and current time.
    """
    now = now_utc()
    for b in bets:
        status = b.get("status", "pending")
        if status in ("win", "loss", "push"):
            continue

        ct_str = b.get("commence_time")
        ct = parse_datetime(ct_str) if ct_str else None
        if ct and ct <= now:
            b["status"] = "open"
        else:
            b["status"] = "pending"


def build_pick_cards(bets: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group active bets (open+pending) by sport key for card display.
    """
    cards: Dict[str, List[Dict[str, Any]]] = {}
    for b in bets:
        if b.get("status") not in ("open", "pending"):
            continue
        sport_key = b.get("sport_key") or ""
        if not sport_key:
            continue
        sport_list = cards.setdefault(sport_key, [])
        sport_list.append({
            "sport": b.get("sport"),
            "event_id": b.get("event_id"),
            "commence_time": b.get("commence_time"),
            "matchup": b.get("matchup"),
            "pick_type": b.get("pick_type"),
            "pick": b.get("pick"),
            "odds": b.get("odds"),
            "stake": b.get("stake"),
            "ev": b.get("ev"),
            "smart_score": b.get("smart_score"),
            "status": b.get("status"),
            "result": b.get("result"),
            "profit": b.get("profit"),
        })
    # Sort each sport's cards by Smart Score desc
    for skey in cards:
        cards[skey].sort(key=lambda x: (x.get("smart_score") or 0.0), reverse=True)
    return cards


def build_parlay_card(bets: List[Dict[str, Any]], max_legs: int = 5) -> Dict[str, Any]:
    """
    Build Top-N EV parlay from highest-EV active bets with unique events.
    """
    # Filter for active bets
    active = [b for b in bets if b.get("status") in ("open", "pending")]
    # Sort by EV descending
    active.sort(key=lambda x: (x.get("ev") or 0.0), reverse=True)

    legs: List[Dict[str, Any]] = []
    seen_events = set()

    for b in active:
        eid = b.get("event_id")
        if not eid or eid in seen_events:
            continue
        seen_events.add(eid)
        legs.append(b)
        if len(legs) >= max_legs:
            break

    picks = []
    total_stake = 0.0
    total_ev = 0.0

    for b in legs:
        total_stake += float(b.get("stake", 0.0))
        total_ev += float(b.get("ev") or 0.0)
        picks.append({
            "sport": b.get("sport"),
            "matchup": b.get("matchup"),
            "pick": b.get("pick"),
            "odds": b.get("odds"),
            "stake": b.get("stake"),
            "ev": b.get("ev"),
            "smart_score": b.get("smart_score"),
            "commence_time": b.get("commence_time"),
        })

    return {
        "legs": len(picks),
        "total_stake": round(total_stake, 2),
        "total_ev": round(total_ev, 3),
        "picks": picks,
    }


def build_placed_bets_view(bets: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Build open/pending/graded buckets for frontend display.
    """
    buckets = {"open": [], "pending": [], "graded": []}

    for b in bets:
        status = b.get("status")
        view = {
            "sport_key": b.get("sport_key"),
            "sport": b.get("sport"),
            "event_id": b.get("event_id"),
            "commence_time": b.get("commence_time"),
            "home_team": b.get("home_team"),
            "away_team": b.get("away_team"),
            "matchup": b.get("matchup"),
            "pick_type": b.get("pick_type"),
            "pick": b.get("pick"),
            "odds": b.get("odds"),
            "fair_prob": b.get("fair_prob"),
            "market_prob": b.get("market_prob"),
            "ev": b.get("ev"),
            "smart_score": b.get("smart_score"),
            "stake": b.get("stake"),
            "status": status,
            "result": b.get("result"),
            "profit": b.get("profit"),
            "created_at": b.get("created_at"),
            "source": b.get("source"),
        }

        if status in ("open",):
            buckets["open"].append(view)
        elif status in ("pending",):
            buckets["pending"].append(view)
        else:
            buckets["graded"].append(view)

    return buckets


def build_data_json(
    placed_bets: List[Dict[str, Any]],
    bankroll: float,
    performance: Dict[str, Any],
) -> Dict[str, Any]:
    open_count = sum(1 for b in placed_bets if b.get("status") == "open")
    pending_count = sum(1 for b in placed_bets if b.get("status") == "pending")
    graded_count = sum(1 for b in placed_bets if b.get("status") in ("win", "loss", "push"))

    return {
        "generated_at": now_utc().isoformat(),
        "bankroll": round(bankroll, 2),
        "open_bets": open_count,
        "pending_bets": pending_count,
        "graded_bets": graded_count,
        "performance": performance,
        "pick_cards": build_pick_cards(placed_bets),
        "parlay_card": build_parlay_card(placed_bets),
        "placed_bets": build_placed_bets_view(placed_bets),
    }


def build_scores_json(scores_by_sport: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Build scoreboard payload for frontend ticker:
    {
      "scores": [
        { "league": "NHL", "event": "Team A @ Team B", "score": "3-2", "status": "final" }
      ]
    }
    """
    scores_payload: List[Dict[str, Any]] = []
    now = now_utc()

    for sport_key, events in scores_by_sport.items():
        pretty = SPORTS.get(sport_key, {}).get("pretty", sport_key)

        for ev in events:
            home = ev.get("home_team", "Home")
            away = ev.get("away_team", "Away")
            completed = bool(ev.get("completed"))

            status = "final" if completed else "scheduled"
            ct = parse_datetime(ev.get("commence_time", ""))
            if not completed and ct and ct <= now:
                status = "live"

            score_str = ""
            scores = ev.get("scores")
            if isinstance(scores, list) and len(scores) >= 2:
                # Try to construct "away-home" scoreboard string
                home_score = away_score = None
                for s in scores:
                    name = s.get("name")
                    try:
                        val = int(s.get("score", 0))
                    except Exception:
                        continue
                    if name == home:
                        home_score = val
                    elif name == away:
                        away_score = val
                if home_score is not None and away_score is not None:
                    score_str = f"{away_score}-{home_score}"

            scores_payload.append({
                "league": pretty,
                "event": f"{away} @ {home}",
                "score": score_str,
                "status": status,
            })

    return {"scores": scores_payload}


# =============================================================================
# MAIN
# =============================================================================


def main() -> None:
    logging.info("=== SmartPicks v4 run starting ===")

    config = load_config()
    api_key = config["api_key"]
    base_bankroll = float(config.get("BASE_BANKROLL", 200.0))
    unit_fraction = float(config.get("UNIT_FRACTION", 0.01))
    base_stake = round(base_bankroll * unit_fraction, 2)

    logging.info(
        "Using base_bankroll=%.2f, unit_fraction=%.4f, base_stake=%.2f",
        base_bankroll,
        unit_fraction,
        base_stake,
    )

    # -------------------------------------------------------------------------
    # Load existing bets
    # -------------------------------------------------------------------------
    placed_bets = load_placed_bets()
    logging.info("Loaded %d placed bets", len(placed_bets))

    # Normalize any missing fields for legacy bets
    for b in placed_bets:
        skey = b.get("sport_key")
        if not skey:
            pretty = b.get("sport")
            for key, cfg in SPORTS.items():
                if cfg["pretty"] == pretty:
                    b["sport_key"] = key
                    break
        if not b.get("created_at"):
            b["created_at"] = now_utc().isoformat()
        if b.get("source") is None:
            b["source"] = "auto"

    # -------------------------------------------------------------------------
    # Fetch scores & grade existing bets
    # -------------------------------------------------------------------------
    scores_by_sport: Dict[str, List[Dict[str, Any]]] = {}
    for sport_key in SPORTS.keys():
        logging.info("Fetching scores for %s (last %d days)...", sport_key, SCORES_DAYS_FROM)
        scores_by_sport[sport_key] = fetch_scores_for_sport(sport_key, api_key, SCORES_DAYS_FROM)

    # Grade in-place
    grade_bets(placed_bets, scores_by_sport)
    # Normalize pending vs open based on time
    update_open_pending_statuses(placed_bets)

    # -------------------------------------------------------------------------
    # Performance & bankroll after grading
    # -------------------------------------------------------------------------
    performance = build_performance(placed_bets)
    save_performance_metrics(performance)
    overall = performance.get("overall", {})
    total_profit = float(overall.get("total_profit", 0.0))
    bankroll = base_bankroll + total_profit

    logging.info(
        "Performance: total_bets=%s, wins=%s, losses=%s, pushes=%s, profit=%.2f, bankroll=%.2f",
        overall.get("total_bets"),
        overall.get("wins"),
        overall.get("losses"),
        overall.get("pushes"),
        total_profit,
        bankroll,
    )

    # -------------------------------------------------------------------------
    # Fetch odds & build new candidate bets (respect risk rules)
    # -------------------------------------------------------------------------
    new_bets: List[Dict[str, Any]] = []
    current_open = count_open_bets(placed_bets)
    if current_open >= MAX_OPEN_BETS:
        logging.info(
            "Risk rule: max_open_bets=%d reached (current=%d); no new bets will be added.",
            MAX_OPEN_BETS,
            current_open,
        )
    else:
        for sport_key in SPORTS.keys():
            logging.info("Fetching odds for %s...", sport_key)
            odds_events = fetch_odds_for_sport(sport_key, api_key)
            logging.info("Received %d events for %s", len(odds_events), sport_key)

            candidates = process_sport_odds(sport_key, odds_events, base_stake)
            logging.info("Built %d candidates for %s", len(candidates), sport_key)

            for bet in candidates:
                if count_open_bets(placed_bets) >= MAX_OPEN_BETS:
                    logging.info(
                        "Risk rule: max_open_bets=%d reached while adding; stopping.",
                        MAX_OPEN_BETS,
                    )
                    break
                if is_duplicate_event(bet, placed_bets):
                    continue
                placed_bets.append(bet)
                new_bets.append(bet)

    if new_bets:
        logging.info("Added %d new bets to placed_bets.", len(new_bets))
    else:
        logging.info("No new bets added this run.")

    # After adding new bets, refresh performance (but do not re-grade)
    performance = build_performance(placed_bets)
    save_performance_metrics(performance)
    overall = performance.get("overall", {})
    total_profit = float(overall.get("total_profit", 0.0))
    bankroll = base_bankroll + total_profit

    # Persist bets & history
    save_placed_bets(placed_bets)
    # Log *all* bets each run to history (simple, append-only)
    append_bets_to_history(new_bets)

    # -------------------------------------------------------------------------
    # Build frontend JSONs
    # -------------------------------------------------------------------------
    data_payload = build_data_json(placed_bets, bankroll, performance)
    write_json(DATA_JSON_PATH, data_payload)
    logging.info("Wrote %s", DATA_JSON_PATH)

    scores_payload = build_scores_json(scores_by_sport)
    write_json(SCORES_JSON_PATH, scores_payload)
    logging.info("Wrote %s", SCORES_JSON_PATH)

    logging.info("=== SmartPicks v4 run complete ===")


if __name__ == "__main__":
    main()
