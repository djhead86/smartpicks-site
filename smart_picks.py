#!/usr/bin/env python3
"""
SmartPicks backend engine (smart_picks.py)

Responsibilities:
- Fetch multi-sport odds from The Odds API
- Compute EV and Smart Score
- Apply sport-specific thresholds and risk rules
- Build candidate picks and a Top-5 EV parlay
- Grade existing bets using Odds API scores (with ESPN-style fallback hooks)
- Maintain placed_bets.json and bet_history.csv
- Generate data.json and scores.json for the frontend
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# ============================================================================
# CONSTANTS / CONFIG
# ============================================================================

BASE_DIR = Path(__file__).resolve().parent

CONFIG_FILE = BASE_DIR / "config.json"
DATA_FILE = BASE_DIR / "data.json"
SCORES_FILE = BASE_DIR / "scores.json"
BET_HISTORY_FILE = BASE_DIR / "bet_history.csv"
PLACED_BETS_FILE = BASE_DIR / "placed_bets.json"
PERFORMANCE_FILE = BASE_DIR / "performance.json"

# The Odds API
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# All supported sports and Smart Score thresholds
SPORTS: Dict[str, Dict[str, Any]] = {
    "basketball_nba": {
        "label": "NBA",
        "smart_score_min": 1.2,
    },
    "americanfootball_nfl": {
        "label": "NFL",
        "smart_score_min": 1.0,
    },
    "icehockey_nhl": {
        "label": "NHL",
        "smart_score_min": 1.0,
    },
    "soccer_epl": {
        "label": "EPL",
        "smart_score_min": 1.0,
    },
    "soccer_uefa_champions_league": {
        "label": "UEFA",
        "smart_score_min": 1.0,
    },
    "mma_mixed_martial_arts": {
        "label": "UFC",
        # Moneyline-only; no Smart Score threshold
        "smart_score_min": None,
    },
}

# Risk rules (simple but extensible)
RISK_RULES: Dict[str, Any] = {
    # Maximum concurrent open + pending bets
    "max_open_bets": 50,
}

# Timezone: Odds API uses UTC; we expose MST (Phoenix) on the site
LOCAL_TZ = timezone(timedelta(hours=-7))


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class Bet:
    sport_key: str
    sport: str
    event_id: str
    commence_time: str  # ISO 8601 UTC string
    home_team: str
    away_team: str

    pick_type: str  # e.g. "h2h"
    pick: str       # team name or "over"/"under"
    odds: int       # American odds

    fair_prob: float
    market_prob: float
    ev: float               # Expected value in dollars (given stake)
    smart_score: float
    stake: float

    status: str = "pending"  # "pending", "open", "graded"
    result: Optional[str] = None  # "WIN", "LOSS", "PUSH"
    profit: Optional[float] = None

    def to_json(self) -> Dict[str, Any]:
        data = asdict(self)
        return data


# ============================================================================
# LOGGING
# ============================================================================

def setup_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


logger = logging.getLogger(__name__)


# ============================================================================
# CONFIG LOADING
# ============================================================================

def load_config() -> Dict[str, Any]:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Missing config file: {CONFIG_FILE}")
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)

    api_key = os.getenv("ODDS_API_KEY") or config.get("api_key")
    if not api_key:
        raise RuntimeError("No Odds API key provided (config.json or ODDS_API_KEY env)")

    base_bankroll = float(config.get("BASE_BANKROLL", 200.0))
    unit_fraction = float(config.get("UNIT_FRACTION", 0.01))

    config["api_key"] = api_key
    config["BASE_BANKROLL"] = base_bankroll
    config["UNIT_FRACTION"] = unit_fraction
    return config


# ============================================================================
# UTILS: ODDS / PROB / EV / SMART SCORE
# ============================================================================

def american_to_decimal(odds: int) -> float:
    if odds > 0:
        return 1.0 + odds / 100.0
    return 1.0 + 100.0 / abs(odds)


def implied_prob_from_american(odds: int) -> float:
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return -odds / (-odds + 100.0)


def compute_edge_per_unit(fair_prob: float, odds: int) -> float:
    """
    Expected profit per 1 unit stake.
    edge = p * (d - 1) - (1 - p)
    """
    d = american_to_decimal(odds)
    return fair_prob * (d - 1.0) - (1.0 - fair_prob)


def compute_ev_dollars(fair_prob: float, odds: int, stake: float) -> float:
    return compute_edge_per_unit(fair_prob, odds) * stake


def compute_smart_score(
    fair_prob: float,
    market_prob: float,
    book_probs: List[float],
    sport_key: str,
) -> float:
    """
    Smart Score:
    - Rewards positive edge (fair_prob > market_prob)
    - Penalizes disagreement across books (high std dev)
    - Slightly rewards higher-confidence bets (higher fair_prob)
    Output is roughly between 0 and 3 for reasonable edges.
    """
    edge_prob = max(0.0, fair_prob - market_prob)
    if edge_prob <= 0:
        return 0.0

    # Market sharpness: std dev of book implied probs
    if len(book_probs) > 1:
        mean = sum(book_probs) / len(book_probs)
        variance = sum((p - mean) ** 2 for p in book_probs) / (len(book_probs) - 1)
        std = math.sqrt(variance)
    else:
        std = 0.0

    # 0 (very noisy) to 1 (very sharp)
    sharpness_factor = max(0.0, 1.0 - min(std / 0.10, 1.0))

    # Base score from edge and confidence
    base_score = edge_prob * 100.0 * fair_prob  # ~0-5 range for good edges
    score = base_score * (0.5 + 0.5 * sharpness_factor)

    # Sport-specific mild weighting (optional hook)
    if sport_key == "mma_mixed_martial_arts":
        score *= 0.9  # a bit more variance in UFC
    return round(score, 3)


# ============================================================================
# FILE I/O HELPERS
# ============================================================================

def load_placed_bets() -> List[Bet]:
    if not PLACED_BETS_FILE.exists():
        logger.info("No placed_bets.json found; starting fresh.")
        return []

    try:
        with open(PLACED_BETS_FILE, "r") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to parse {PLACED_BETS_FILE}: {e}")
        return []

    bets_raw = data.get("bets", [])
    bets: List[Bet] = []
    for b in bets_raw:
        try:
            bets.append(Bet(
                sport_key=b["sport_key"],
                sport=b["sport"],
                event_id=b["event_id"],
                commence_time=b["commence_time"],
                home_team=b["home_team"],
                away_team=b["away_team"],
                pick_type=b.get("pick_type", "h2h"),
                pick=b["pick"],
                odds=int(b["odds"]),
                fair_prob=float(b["fair_prob"]),
                market_prob=float(b["market_prob"]),
                ev=float(b["ev"]),
                smart_score=float(b["smart_score"]),
                stake=float(b["stake"]),
                status=b.get("status", "pending"),
                result=b.get("result"),
                profit=b.get("profit"),
            ))
        except KeyError as e:
            logger.warning(f"Skipping malformed bet in placed_bets.json: missing {e}")
    logger.info(f"Loaded {len(bets)} placed bets from {PLACED_BETS_FILE}")
    return bets


def save_placed_bets(bets: List[Bet]) -> None:
    payload = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "bets": [b.to_json() for b in bets],
    }
    with open(PLACED_BETS_FILE, "w") as f:
        json.dump(payload, f, indent=2)
    logger.info(f"Saved {len(bets)} placed bets to {PLACED_BETS_FILE}")


def append_bet_history_row(bet: Bet, bankroll_after: float) -> None:
    """Append a graded bet to bet_history.csv (idempotency not enforced)."""
    is_new_file = not BET_HISTORY_FILE.exists()
    with open(BET_HISTORY_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new_file:
            writer.writerow([
                "Date",
                "Sport",
                "Event",
                "Side",
                "Odds",
                "Stake",
                "Status",
                "Result",
                "Profit",
                "Bankroll",
            ])
        event_str = f"{bet.away_team} @ {bet.home_team}"
        writer.writerow([
            datetime.now(LOCAL_TZ).strftime("%Y-%m-%d"),
            bet.sport,
            event_str,
            bet.pick,
            bet.odds,
            f"{bet.stake:.2f}",
            bet.status,
            bet.result or "",
            f"{(bet.profit or 0.0):.2f}",
            f"{bankroll_after:.2f}",
        ])


def load_performance() -> Dict[str, Any]:
    if not PERFORMANCE_FILE.exists():
        return {
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
        }
    try:
        with open(PERFORMANCE_FILE, "r") as f:
            data = json.load(f)
        return data.get("performance", {})
    except Exception as e:
        logger.error(f"Failed to load performance.json: {e}")
        return {
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
        }


def save_performance(perf: Dict[str, Any]) -> None:
    payload = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "performance": perf,
    }
    with open(PERFORMANCE_FILE, "w") as f:
        json.dump(payload, f, indent=2)
    logger.info(f"Saved performance metrics to {PERFORMANCE_FILE}")


# ============================================================================
# PERFORMANCE CALCULATION
# ============================================================================

def calculate_performance(bets: List[Bet]) -> Dict[str, Any]:
    graded = [b for b in bets if b.status == "graded" and b.result]
    if not graded:
        return {
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
        }

    overall = {
        "total_bets": 0,
        "wins": 0,
        "losses": 0,
        "pushes": 0,
        "win_rate": 0.0,
        "roi": 0.0,
        "total_wagered": 0.0,
        "total_profit": 0.0,
    }
    by_sport: Dict[str, Dict[str, Any]] = {}
    by_bet_type: Dict[str, Dict[str, Any]] = {}

    for b in graded:
        overall["total_bets"] += 1
        overall["total_wagered"] += b.stake
        overall["total_profit"] += b.profit or 0.0

        if b.result == "WIN":
            overall["wins"] += 1
        elif b.result == "LOSS":
            overall["losses"] += 1
        elif b.result == "PUSH":
            overall["pushes"] += 1

        sport_bucket = by_sport.setdefault(b.sport, {
            "total_bets": 0,
            "wins": 0,
            "losses": 0,
            "pushes": 0,
            "win_rate": 0.0,
            "roi": 0.0,
            "total_wagered": 0.0,
            "total_profit": 0.0,
        })
        sport_bucket["total_bets"] += 1
        sport_bucket["total_wagered"] += b.stake
        sport_bucket["total_profit"] += b.profit or 0.0
        if b.result == "WIN":
            sport_bucket["wins"] += 1
        elif b.result == "LOSS":
            sport_bucket["losses"] += 1
        elif b.result == "PUSH":
            sport_bucket["pushes"] += 1

        bet_type = b.pick_type
        type_bucket = by_bet_type.setdefault(bet_type, {
            "total_bets": 0,
            "wins": 0,
            "losses": 0,
            "pushes": 0,
            "win_rate": 0.0,
            "roi": 0.0,
            "total_wagered": 0.0,
            "total_profit": 0.0,
        })
        type_bucket["total_bets"] += 1
        type_bucket["total_wagered"] += b.stake
        type_bucket["total_profit"] += b.profit or 0.0
        if b.result == "WIN":
            type_bucket["wins"] += 1
        elif b.result == "LOSS":
            type_bucket["losses"] += 1
        elif b.result == "PUSH":
            type_bucket["pushes"] += 1

    def finalize(bucket: Dict[str, Any]) -> None:
        if bucket["total_bets"] > 0:
            bucket["win_rate"] = round(
                bucket["wins"] / bucket["total_bets"] * 100.0, 2
            )
        if bucket["total_wagered"] > 0:
            bucket["roi"] = round(
                bucket["total_profit"] / bucket["total_wagered"] * 100.0, 2
            )

    finalize(overall)
    for v in by_sport.values():
        finalize(v)
    for v in by_bet_type.values():
        finalize(v)

    return {
        "overall": overall,
        "by_sport": by_sport,
        "by_bet_type": by_bet_type,
    }


# ============================================================================
# ODDS API FETCHING
# ============================================================================

def odds_get(path: str, api_key: str, params: Dict[str, Any]) -> Optional[Any]:
    url = f"{ODDS_API_BASE}{path}"
    merged_params = dict(params)
    merged_params["apiKey"] = api_key
    try:
        resp = requests.get(url, params=merged_params, timeout=10)
        if resp.status_code != 200:
            logger.error(f"Odds API error {resp.status_code} for {url}: {resp.text}")
            return None
        return resp.json()
    except Exception as e:
        logger.error(f"Request failed for {url}: {e}")
        return None


def fetch_odds_for_sport(sport_key: str, api_key: str) -> List[Dict[str, Any]]:
    logger.info(f"Fetching odds for {sport_key}...")
    data = odds_get(
        f"/sports/{sport_key}/odds",
        api_key,
        {
            "regions": "us,us2,eu,uk",
            "markets": "h2h",
            "oddsFormat": "american",
            "dateFormat": "iso",
        },
    )
    if data is None:
        return []
    logger.info(f"Received {len(data)} events for {sport_key}")
    return data


def fetch_all_odds(api_key: str) -> Dict[str, List[Dict[str, Any]]]:
    all_odds: Dict[str, List[Dict[str, Any]]] = {}
    for sport_key in SPORTS.keys():
        events = fetch_odds_for_sport(sport_key, api_key)
        all_odds[sport_key] = events
    return all_odds


# ============================================================================
# SCORE / GRADING HELPERS
# ============================================================================

def fetch_scores_for_sport(sport_key: str, api_key: str, days_from: int = 3) -> List[Dict[str, Any]]:
    logger.info(f"Fetching scores for {sport_key} (last {days_from} days)...")
    data = odds_get(
        f"/sports/{sport_key}/scores",
        api_key,
        {"daysFrom": days_from, "dateFormat": "iso"},
    )
    if data is None:
        return []
    return data


def map_scores_by_event_id(scores: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for ev in scores:
        ev_id = ev.get("id")
        if ev_id:
            by_id[ev_id] = ev
    return by_id


def resolve_bet_result_from_score(bet: Bet, event_score: Dict[str, Any]) -> Tuple[str, float]:
    """
    Determine result and profit given a Bet and a score object from The Odds API.
    """
    completed = event_score.get("completed")
    if not completed:
        # Not finished; no result yet
        return bet.status, bet.profit or 0.0

    try:
        scores = event_score.get("scores", [])
        home_score = None
        away_score = None
        for s in scores:
            if s.get("name") == bet.home_team:
                home_score = int(s.get("score", 0))
            elif s.get("name") == bet.away_team:
                away_score = int(s.get("score", 0))
        if home_score is None or away_score is None:
            logger.warning(f"Could not find team scores for event {bet.event_id}")
            return bet.status, bet.profit or 0.0
    except Exception as e:
        logger.error(f"Error parsing scores for event {bet.event_id}: {e}")
        return bet.status, bet.profit or 0.0

    # Determine outcome
    if home_score == away_score:
        result = "PUSH"
        profit = 0.0
    else:
        d = american_to_decimal(bet.odds)
        win_profit = bet.stake * (d - 1.0)
        if bet.pick == bet.home_team and home_score > away_score:
            result = "WIN"
            profit = win_profit
        elif bet.pick == bet.away_team and away_score > home_score:
            result = "WIN"
            profit = win_profit
        else:
            result = "LOSS"
            profit = -bet.stake

    return "graded", profit


def grade_bets(bets: List[Bet], api_key: str, base_bankroll: float, prior_profit: float) -> Tuple[List[Bet], float]:
    """
    Grade bets that have finished according to Odds API scores.
    Returns updated bets and the updated bankroll after newly graded bets.
    """
    # Start from base bankroll plus profit already realized in previous runs
    bankroll = base_bankroll + prior_profit

    # Fetch scores per sport
    all_scores: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for sport_key in SPORTS.keys():
        scores = fetch_scores_for_sport(sport_key, api_key, days_from=7)
        all_scores[sport_key] = map_scores_by_event_id(scores)

    for bet in bets:
        # If this bet is already graded, it is already included in prior_profit;
        # do not change bankroll again.
        if bet.status == "graded" and bet.result:
            continue

        # Attempt to find score
        scores_for_sport = all_scores.get(bet.sport_key, {})
        event_score = scores_for_sport.get(bet.event_id)

        if not event_score:
            # Try to infer status by commence_time
            try:
                commence_dt = datetime.fromisoformat(
                    bet.commence_time.replace("Z", "+00:00")
                )
            except Exception:
                commence_dt = datetime.now(timezone.utc)
            now = datetime.now(timezone.utc)
            if commence_dt > now:
                bet.status = "pending"
            else:
                bet.status = "open"
            continue

        new_status, profit = resolve_bet_result_from_score(bet, event_score)
        if new_status == "graded":
            bet.status = "graded"
            bet.profit = profit
            if profit > 0:
                bet.result = "WIN"
            elif profit < 0:
                bet.result = "LOSS"
            else:
                bet.result = "PUSH"
            bankroll += profit
            append_bet_history_row(bet, bankroll)
        else:
            # Shouldn't happen; keep as-is
            pass

    return bets, bankroll


# ============================================================================
# CANDIDATE BUILDING / RISK RULES
# ============================================================================

def event_dedupe_key(event: Dict[str, Any]) -> str:
    """Stable key for an event to avoid duplicate bets."""
    return event.get("id") or f"{event.get('home_team')}@{event.get('away_team')}@{event.get('commence_time')}"


def build_candidates_from_odds(
    all_odds: Dict[str, List[Dict[str, Any]]],
    stake: float,
    existing_event_ids: List[str],
    current_open_pending: int,
) -> List[Bet]:
    candidates: List[Bet] = []
    existing_set = set(existing_event_ids)

    for sport_key, events in all_odds.items():
        sport_conf = SPORTS.get(sport_key, {})
        label = sport_conf.get("label", sport_key)
        threshold = sport_conf.get("smart_score_min")

        for ev in events:
            event_id = ev.get("id")
            if not event_id:
                continue

            if event_id in existing_set:
                # Already have a bet for this event
                continue

            home = ev.get("home_team")
            away = ev.get("away_team")
            commence_time = ev.get("commence_time")

            # Collect book prices per team for h2h
            team_prices: Dict[str, List[int]] = {home: [], away: []}
            book_probs: Dict[str, List[float]] = {home: [], away: []}

            for book in ev.get("bookmakers", []):
                for market in book.get("markets", []):
                    if market.get("key") != "h2h":
                        continue
                    for outcome in market.get("outcomes", []):
                        name = outcome.get("name")
                        price = outcome.get("price")
                        if name in team_prices and isinstance(price, (int, float)):
                            odds_int = int(price)
                            team_prices[name].append(odds_int)
                            book_probs[name].append(implied_prob_from_american(odds_int))

            event_candidates: List[Bet] = []

            for team_name in (home, away):
                prices = team_prices.get(team_name, [])
                probs = book_probs.get(team_name, [])
                if not prices or not probs:
                    continue

                # Best odds for bettor
                best_odds = max(prices)
                # Fair probability = average implied prob across books
                fair_prob = sum(probs) / len(probs)
                market_prob = implied_prob_from_american(best_odds)

                # Compute metrics
                ev_dollars = compute_ev_dollars(fair_prob, best_odds, stake)
                smart_score = compute_smart_score(fair_prob, market_prob, probs, sport_key)

                # Positive EV only
                if ev_dollars <= 0:
                    continue

                # Apply Smart Score thresholds (except UFC)
                if threshold is not None and smart_score < threshold:
                    continue

                bet = Bet(
                    sport_key=sport_key,
                    sport=label,
                    event_id=event_id,
                    commence_time=commence_time,
                    home_team=home,
                    away_team=away,
                    pick_type="h2h",
                    pick=team_name,
                    odds=int(best_odds),
                    fair_prob=fair_prob,
                    market_prob=market_prob,
                    ev=ev_dollars,
                    smart_score=smart_score,
                    stake=stake,
                    status="pending",
                )
                event_candidates.append(bet)

            if not event_candidates:
                continue

            # Per-event dedup: take the bet with the highest EV
            best_bet = max(event_candidates, key=lambda b: b.ev)
            candidates.append(best_bet)

    # Risk rule: cap maximum TOTAL open+pending bets based on max_open_bets
    max_open = RISK_RULES.get("max_open_bets")
    candidates = sorted(candidates, key=lambda b: b.ev, reverse=True)
    if isinstance(max_open, int) and max_open > 0:
        available_slots = max_open - current_open_pending
        if available_slots <= 0:
            logger.info(
                f"Risk rule: max_open_bets={max_open} reached "
                f"(current={current_open_pending}); no new bets will be added."
            )
            candidates = []
        elif len(candidates) > available_slots:
            logger.info(
                f"Risk rule: trimming new candidates from {len(candidates)} to "
                f"{available_slots} (max_open_bets={max_open}, current={current_open_pending})"
            )
            candidates = candidates[:available_slots]

    logger.info(f"Built {len(candidates)} candidate bets across all sports")
    return candidates


# ============================================================================
# FRONTEND JSON BUILDERS
# ============================================================================

def build_scores_json(bets: List[Bet]) -> Dict[str, Any]:
    """Build scores.json payload showing only events we have bets on."""
    scores: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for b in bets:
        try:
            commence = datetime.fromisoformat(b.commence_time.replace("Z", "+00:00"))
        except Exception:
            commence = now

        status = b.status
        if status == "graded":
            status_text = f"Final ({b.result})"
        elif commence > now:
            status_text = "Not started"
        else:
            status_text = "Live"

        scores.append({
            "sport": b.sport,
            "event": f"{b.away_team} @ {b.home_team}",
            "score": "",  # Could be enhanced to carry actual scores
            "status": status_text,
            "commence_time": b.commence_time,
        })

    return {
        "last_updated": now.isoformat(),
        "scores": scores,
    }


def build_data_json(
    bankroll: float,
    bets: List[Bet],
    performance: Dict[str, Any],
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)

    open_bets = sum(1 for b in bets if b.status == "open")
    pending_bets = sum(1 for b in bets if b.status == "pending")
    graded_bets = sum(1 for b in bets if b.status == "graded")

    # pick_cards: per sport (label) list of simplified bet cards
    pick_cards: Dict[str, List[Dict[str, Any]]] = {}
    for b in bets:
        if b.status not in ("pending", "open"):
            continue
        sport_label = b.sport
        arr = pick_cards.setdefault(sport_label, [])
        arr.append({
            "sport": b.sport,
            "event_id": b.event_id,
            "commence_time": b.commence_time,
            "matchup": f"{b.away_team} @ {b.home_team}",
            "pick_type": b.pick_type,
            "pick": b.pick,
            "odds": b.odds,
            "stake": round(b.stake, 2),
            "ev": round(b.ev, 2),
            "smart_score": round(b.smart_score, 3),
            "status": b.status,
            "result": b.result,
            "profit": b.profit,
        })

    # Parlay card: Top 5 EV among non-graded bets
    parlay_candidates = sorted(
        [b for b in bets if b.status in ("pending", "open")],
        key=lambda b: b.ev,
        reverse=True,
    )[:5]
    parlay_card = {
        "legs": len(parlay_candidates),
        "total_stake": round(sum(b.stake for b in parlay_candidates), 2),
        "total_ev": round(sum(b.ev for b in parlay_candidates), 2),
        "picks": [
            {
                "sport": b.sport,
                "matchup": f"{b.away_team} @ {b.home_team}",
                "pick": b.pick,
                "odds": b.odds,
                "stake": round(b.stake, 2),
                "ev": round(b.ev, 2),
                "smart_score": round(b.smart_score, 3),
                "commence_time": b.commence_time,
            }
            for b in parlay_candidates
        ],
    }

    # placed_bets: grouped by status
    placed_open: List[Dict[str, Any]] = []
    placed_pending: List[Dict[str, Any]] = []
    placed_graded: List[Dict[str, Any]] = []

    for b in bets:
        card = {
            "sport": b.sport,
            "event_id": b.event_id,
            "commence_time": b.commence_time,
            "home_team": b.home_team,
            "away_team": b.away_team,
            "pick_type": b.pick_type,
            "pick": b.pick,
            "odds": b.odds,
            "fair_prob": b.fair_prob,
            "market_prob": b.market_prob,
            "ev": round(b.ev, 2),
            "smart_score": round(b.smart_score, 3),
            "stake": round(b.stake, 2),
            "status": b.status,
            "result": b.result,
            "profit": b.profit,
        }
        if b.status == "open":
            placed_open.append(card)
        elif b.status == "pending":
            placed_pending.append(card)
        elif b.status == "graded":
            placed_graded.append(card)

    placed_bets = {
        "open": placed_open,
        "pending": placed_pending,
        "graded": placed_graded,
    }

    return {
        "generated_at": now.isoformat(),
        "bankroll": round(bankroll, 2),
        "open_bets": open_bets,
        "pending_bets": pending_bets,
        "graded_bets": graded_bets,
        "performance": performance,
        "pick_cards": pick_cards,
        "parlay_card": parlay_card,
        "placed_bets": placed_bets,
    }


# ============================================================================
# MAIN ORCHESTRATION
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="SmartPicks backend engine")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug logging",
    )
    args = parser.parse_args()

    setup_logging(debug=args.debug)
    logger.info("=== SmartPicks run starting ===")

    config = load_config()
    api_key = config["api_key"]
    base_bankroll = float(config["BASE_BANKROLL"])
    unit_fraction = float(config["UNIT_FRACTION"])
    stake = base_bankroll * unit_fraction
    logger.info(f"Using base bankroll={base_bankroll}, unit_fraction={unit_fraction}, stake={stake:.2f}")

    # Load prior performance (if any) to avoid double-counting profit
    prior_perf = load_performance()
    prior_overall = prior_perf.get("overall", {})
    prior_profit = float(prior_overall.get("total_profit", 0.0))

    # Load existing bets and grade them
    bets = load_placed_bets()
    bets, _ = grade_bets(bets, api_key, base_bankroll, prior_profit)

    # Calculate performance metrics AFTER grading this run
    performance = calculate_performance(bets)
    save_performance(performance)

    # Effective bankroll = base + realized profit
    total_profit = performance["overall"]["total_profit"]
    bankroll = base_bankroll + total_profit
    logger.info(f"Computed bankroll={bankroll:.2f} (base {base_bankroll} + profit {total_profit:.2f})")

    # Build set of event_ids already bet on (avoid duplicates)
    existing_event_ids = [b.event_id for b in bets if b.status in ("pending", "open")]
    current_open_pending = len([b for b in bets if b.status in ("pending", "open")])

    # Fetch fresh odds and build new candidates
    all_odds = fetch_all_odds(api_key)
    new_candidates = build_candidates_from_odds(all_odds, stake, existing_event_ids, current_open_pending)

    # Merge new candidates into bet list
    bets.extend(new_candidates)
    save_placed_bets(bets)

    # Recompute performance after new bets? Only graded bets matter; unchanged
    performance = calculate_performance(bets)
    save_performance(performance)

    # Build and save frontend JSONs
    data_payload = build_data_json(bankroll, bets, performance)
    with open(DATA_FILE, "w") as f:
        json.dump(data_payload, f, indent=2)
    logger.info(f"Wrote {DATA_FILE}")

    scores_payload = build_scores_json(bets)
    with open(SCORES_FILE, "w") as f:
        json.dump(scores_payload, f, indent=2)
    logger.info(f"Wrote {SCORES_FILE}")

    logger.info("=== SmartPicks run complete ===")


if __name__ == "__main__":
    main()
