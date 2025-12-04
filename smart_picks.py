#!/usr/bin/env python3
"""
SmartPicks v3.1 (clean rebuild)

- Multi-sport odds fetch (The Odds API)
- Event-level deduplication (no new bets on already-bet events)
- Rich bet_history.csv schema with automatic migration
- Simple model for edge & "Smart Score"
- Analytics: ROI, winrate, per-sport stats, streaks, bankroll
- JSON output: bankroll, open bets, history, analytics

Config:
- Expects config.json in same directory (or uses sane defaults).
- API key taken from env ODDS_API_KEY or config.json["api_key"] / variants.
"""

import csv
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# -------------------------------------------------------------------
# Paths & constants
# -------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "config.json"

TIMEZONE_OFFSET_HOURS = -7  # MST-like display (internal is UTC)

BET_HISTORY_COLUMNS = [
    "bet_id",
    "event_id",
    "timestamp",        # ISO UTC
    "date",             # Local display date
    "sport",
    "match",
    "team",
    "market",           # "h2h", "spreads", "totals"
    "line",
    "odds",
    "stake",
    "event_time",       # ISO UTC
    "status",           # "OPEN" / "CLOSED"
    "result",           # "WIN" / "LOSS" / "PUSH" / ""
    "profit",
    "result_timestamp", # ISO UTC
    "bankroll_after",
]

ODDS_BASE_URL = "https://api.the-odds-api.com/v4"

# -------------------------------------------------------------------
# Utility
# -------------------------------------------------------------------

def ts_now_utc() -> datetime:
    return datetime.now(timezone.utc)


def utc_to_local_mst(dt: datetime) -> datetime:
    # crude fixed offset for display
    return dt.astimezone(timezone(timedelta(hours=TIMEZONE_OFFSET_HOURS)))


def american_to_decimal(odds: int) -> float:
    if odds == 0:
        return 1.0
    if odds > 0:
        return 1.0 + odds / 100.0
    return 1.0 + 100.0 / abs(odds)


def implied_probability(odds: int) -> float:
    if odds == 0:
        return 0.5
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)

def fetch_scores_for_sport(
    sport: str, api_key: str, days_from: int
) -> Optional[List[Dict[str, Any]]]:
    """
    Uses The Odds API scores endpoint to pull recent results.
    """
    if not api_key:
        return None

    url = (
        f"{ODDS_BASE_URL}/sports/{sport}/scores"
        f"?apiKey={api_key}"
        f"&daysFrom={days_from}"
    )
    try:
        resp = requests.get(url, timeout=15)
        if not resp.ok:
            print(
                f"[HTTP] Error {resp.status_code} fetching scores for {sport}: {resp.text[:200]}",
                file=sys.stderr,
            )
            return None
        return resp.json()
    except Exception as e:
        print(f"[HTTP] Exception fetching scores for {sport}: {e}", file=sys.stderr)
        return None

def _determine_outcome_from_scores(row: Dict[str, Any], event: Dict[str, Any]) -> Optional[str]:
    """
    Given a bet row and a scores event from The Odds API,
    return 'win', 'loss', 'push' or None if we can't decide.
    """
    market = row.get("market")
    team = row.get("team")
    line_raw = row.get("line")
    line = None
    if line_raw not in (None, "", "None"):
        try:
            line = float(line_raw)
        except ValueError:
            line = None

    home = event.get("home_team")
    away = event.get("away_team")
    scores_list = event.get("scores") or []

    scores = {s.get("name"): s.get("score") for s in scores_list}
    try:
        home_score = float(scores.get(home))
        away_score = float(scores.get(away))
    except (TypeError, ValueError):
        return None

    # H2H
    if market == "h2h":
        if team == home:
            if home_score > away_score:
                return "win"
            elif home_score < away_score:
                return "loss"
            else:
                return "push"
        elif team == away:
            if away_score > home_score:
                return "win"
            elif away_score < home_score:
                return "loss"
            else:
                return "push"
        else:
            return None

    # Spreads: line is spread from perspective of 'team'
    if market == "spreads" and line is not None:
        if team == home:
            margin = (home_score + line) - away_score
        elif team == away:
            margin = (away_score + line) - home_score
        else:
            return None

        if margin > 0:
            return "win"
        elif abs(margin) < 1e-6:
            return "push"
        else:
            return "loss"

    # Totals: team is "over" or "under"
    if market == "totals" and line is not None:
        total = home_score + away_score
        side = (team or "").lower()
        if side == "over":
            if total > line:
                return "win"
            elif abs(total - line) < 1e-6:
                return "push"
            else:
                return "loss"
        elif side == "under":
            if total < line:
                return "win"
            elif abs(total - line) < 1e-6:
                return "push"
            else:
                return "loss"

    return None

def auto_grade_from_scores(config: Config, history_rows: List[Dict[str, Any]]) -> None:
    """
    Look up any OPEN bets whose events have completed, and grade them.
    Uses The Odds API scores endpoint.
    """
    api_key = config.odds_api_key
    if not api_key:
        return

    open_rows = [r for r in history_rows if r.get("status") == "OPEN"]
    if not open_rows:
        return

    sports_needed = {r.get("sport") for r in open_rows if r.get("sport")}
    if not sports_needed:
        return

    # Build index: (sport, event_id) -> event json
    scores_index: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for sport in sports_needed:
        scores_json = fetch_scores_for_sport(sport, api_key, config.days_from_scores)
        for ev in scores_json or []:
            ev_id = ev.get("id")
            if not ev_id:
                continue
            scores_index[(sport, ev_id)] = ev

    changed = False
    for row in open_rows:
        key = (row.get("sport"), row.get("event_id"))
        ev = scores_index.get(key)
        if not ev:
            continue
        if not ev.get("completed"):
            continue

        outcome = _determine_outcome_from_scores(row, ev)
        if not outcome:
            continue

        updated = apply_grade_to_bet(
            history_rows, row["bet_id"], outcome, config.starting_bankroll
        )
        if updated:
            changed = True

    if changed:
        print("[INFO] Auto-graded some open bets from scores.")

# -------------------------------------------------------------------
# Data models
# -------------------------------------------------------------------

@dataclass
class Config:
    starting_bankroll: float
    unit_fraction: float
    sports: List[str]
    bet_history_path: str
    data_output_path: str
    risk_rules: Dict[str, Any]
    odds_api_key: str
    days_from_scores: int

    @classmethod
    def load(cls, path: Path) -> "Config":
        data: Dict[str, Any] = {}
        if path.exists():
            try:
                with path.open("r") as f:
                    data = json.load(f)
            except Exception as e:
                print(f"[WARN] Failed to load config.json: {e}", file=sys.stderr)
        else:
            print("[WARN] config.json not found, using defaults.", file=sys.stderr)

        # Backwards-compatible fields
        starting_bankroll = float(
            data.get("starting_bankroll", data.get("BASE_BANKROLL", 200.0))
        )
        unit_fraction = float(
            data.get("unit_fraction", data.get("UNIT_FRACTION", 0.01))
        )

        sports = data.get(
            "sports",
            ["basketball_nba", "americanfootball_nfl", "soccer_epl"],
        )

        risk_rules = data.get(
            "risk_rules",
            {
                "unit_size": 2.0,
                "max_open_bets": 20,
                "min_ev": 0.02,
                "max_exposure_fraction": 0.10,
            },
        )

        odds_api_key = (
            os.getenv("ODDS_API_KEY")
            or data.get("api_key", "")
            or data.get("ODDS_API_KEY", "")
            or data.get("odds_api_key", "")
        )

        if not odds_api_key:
            print(
                "[WARN] No API key found. Set env ODDS_API_KEY or add 'api_key' to config.json.",
                file=sys.stderr,
            )

        bet_history_path = data.get("bet_history_path", "bet_history.csv")
        data_output_path = data.get("data_output_path", "data.json")
        days_from_scores = int(data.get("days_from_scores", 3))

        return cls(
            starting_bankroll=starting_bankroll,
            unit_fraction=unit_fraction,
            sports=sports,
            bet_history_path=bet_history_path,
            data_output_path=data_output_path,
            risk_rules=risk_rules,
            odds_api_key=odds_api_key,
            days_from_scores=days_from_scores,
        )


@dataclass
class CandidateBet:
    event_id: str
    sport: str
    match: str
    team: str
    market: str
    line: Optional[float]
    odds: int
    stake: float
    event_time_utc: datetime
    book: str
    implied_prob: float
    model_prob: float
    edge: float
    smart_score: float


# -------------------------------------------------------------------
# Odds API client
# -------------------------------------------------------------------
def fetch_odds_for_sport(sport: str, api_key: str) -> Optional[List[Dict[str, Any]]]:
    if not api_key:
        print(f"[WARN] No API key when fetching odds for {sport}", file=sys.stderr)
        return None

    url = (
        f"{ODDS_BASE_URL}/sports/{sport}/odds"
        f"?apiKey={api_key}"
        "&regions=us&markets=h2h,spreads,totals&oddsFormat=american"
    )

    try:
        resp = requests.get(url, timeout=15)
        if not resp.ok:
            print(
                f"[HTTP] Error {resp.status_code} for sport={sport}: {resp.text[:200]}",
                file=sys.stderr,
            )
            return None
        return resp.json()
    except Exception as e:
        print(f"[HTTP] Exception fetching odds for {sport}: {e}", file=sys.stderr)
        return None


# -------------------------------------------------------------------
# bet_history I/O & migration
# -------------------------------------------------------------------

def load_bet_history(path: str) -> List[Dict[str, Any]]:
    p = SCRIPT_DIR / path
    if not p.exists():
        return []

    rows: List[Dict[str, Any]] = []
    with p.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(dict(r))
    # migrate schema
    rows = migrate_history_schema(rows)
    return rows


def migrate_history_schema(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    migrated: List[Dict[str, Any]] = []
    for r in rows:
        new_row = {col: "" for col in BET_HISTORY_COLUMNS}

        # Copy what we can from old row
        for k, v in r.items():
            if k in new_row:
                new_row[k] = v

        # Backfill basics
        new_row["bet_id"] = new_row.get("bet_id") or new_row.get("timestamp") or ""
        new_row["status"] = new_row.get("status") or "OPEN"
        new_row["result"] = new_row.get("result") or ""
        new_row["profit"] = new_row.get("profit") or "0.0"

        migrated.append(new_row)
    return migrated


def save_bet_history(rows: List[Dict[str, Any]], path: str) -> None:
    p = SCRIPT_DIR / path
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=BET_HISTORY_COLUMNS)
        writer.writeheader()
        for r in rows:
            out = {col: r.get(col, "") for col in BET_HISTORY_COLUMNS}
            writer.writerow(out)


# -------------------------------------------------------------------
# Model & candidate generation
# -------------------------------------------------------------------

def naive_model_probability(impl_prob: float, market: str, sport: str) -> float:
    # Slight favourite skew
    if impl_prob > 0.5:
        return min(impl_prob * 1.03, 0.99)
    return max(impl_prob * 0.97, 0.01)


def compute_edge(impl_prob: float, model_prob: float, odds: int) -> float:
    dec = american_to_decimal(odds)
    return model_prob * (dec - 1.0) - (1.0 - model_prob)


def compute_smart_score(edge: float, model_prob: float, odds: int) -> float:
    base = (edge + 0.1) / 0.3
    base = max(0.0, min(base, 1.0))
    conf = model_prob
    score = 100.0 * (0.7 * base + 0.3 * conf)
    return max(0.0, min(score, 100.0))


def build_candidates_from_odds(
    config: Config, history_rows: List[Dict[str, Any]]
) -> List[CandidateBet]:
    api_key = config.odds_api_key
    if not api_key:
        print("[ERROR] No API key. Cannot fetch odds.", file=sys.stderr)
        return []

    # Event-level dedup: don't suggest new bets on events we already have open
    open_event_ids = {
        r.get("event_id")
        for r in history_rows
        if r.get("status") == "OPEN" and r.get("event_id")
    }

    candidates: List[CandidateBet] = []

    for sport in config.sports:
        odds_json = fetch_odds_for_sport(sport, api_key)
        if not odds_json:
            continue

        for game in odds_json:
            event_id = game.get("id")
            if not event_id:
                continue
            if event_id in open_event_ids:
                continue

            home = game.get("home_team", "Home")
            away = game.get("away_team", "Away")
            match = f"{away} @ {home}"

            commence_time = (game.get("commence_time") or "").replace("Z", "+00:00")
            try:
                event_time_utc = datetime.fromisoformat(commence_time).astimezone(
                    timezone.utc
                )
            except Exception:
                event_time_utc = ts_now_utc()

            # FILTER 1: Only games in next 24 hours
            now_utc = ts_now_utc()
            if not (now_utc <= event_time_utc <= now_utc + timedelta(hours=24)):
                continue

            bookmakers = game.get("bookmakers") or []
            best_by_market: Dict[Tuple[str, str], Tuple[int, str, Optional[float]]] = {}

            for bm in bookmakers:
                book = bm.get("title", "Unknown")
                for mk in bm.get("markets") or []:
                    market_key = mk.get("key")
                    outcomes = mk.get("outcomes") or []
                    for o in outcomes:
                        name = o.get("name")
                        price_raw = o.get("price", 0)
                        try:
                            price = int(price_raw)
                        except Exception:
                            continue
                        point = o.get("point")

                        line_val: Optional[float] = None
                        if point not in (None, ""):
                            try:
                                line_val = float(point)
                            except ValueError:
                                line_val = None

                        if market_key == "h2h":
                            outcome_key = name
                        elif market_key == "spreads":
                            outcome_key = name
                        elif market_key == "totals":
                            outcome_key = name.lower()
                        else:
                            continue

                        key = (market_key, outcome_key)
                        current = best_by_market.get(key)
                        if current is None:
                            best_by_market[key] = (price, book, line_val)
                        else:
                            cur_price, _, _ = current
                            if american_to_decimal(price) > american_to_decimal(cur_price):
                                best_by_market[key] = (price, book, line_val)

            # Convert to candidates
            min_ev_rule = float(config.risk_rules.get("min_ev", 0.02))
            min_ev = max(0.02, min_ev_rule)  # at least 2% edge

            for (market_key, outcome_key), (odds, book, line_val) in best_by_market.items():
                if odds == 0:
                    continue

                if market_key == "h2h":
                    team = outcome_key
                    market = "h2h"
                elif market_key == "spreads":
                    team = outcome_key
                    market = "spreads"
                elif market_key == "totals":
                    team = outcome_key
                    market = "totals"
                else:
                    continue

                # FILTER 2: Sweet-spot odds range
                if odds < -300:
                    continue
                if odds > 500:
                    continue

                impl_prob = implied_probability(odds)
                model_prob = naive_model_probability(impl_prob, market, sport)
                edge = compute_edge(impl_prob, model_prob, odds)
                smart_score = compute_smart_score(edge, model_prob, odds)

                # FILTER 3: Minimum EV
                if edge < min_ev:
                    continue

                stake = float(config.risk_rules.get("unit_size", 2.0))

                cand = CandidateBet(
                    event_id=event_id,
                    sport=sport,
                    match=match,
                    team=team,
                    market=market,
                    line=line_val,
                    odds=odds,
                    stake=stake,
                    event_time_utc=event_time_utc,
                    book=book,
                    implied_prob=impl_prob,
                    model_prob=model_prob,
                    edge=edge,
                    smart_score=smart_score,
                )
                candidates.append(cand)

    return candidates


def filter_candidates(
    candidates: List[CandidateBet],
    history_rows: List[Dict[str, Any]],
    config: Config,
) -> List[CandidateBet]:
    max_open = int(config.risk_rules.get("max_open_bets", 20))
    max_exposure_fraction = float(config.risk_rules.get("max_exposure_fraction", 0.10))

    open_rows = [r for r in history_rows if r.get("status") == "OPEN"]
    open_count = len(open_rows)
    bankroll = compute_bankroll_from_history(history_rows, config.starting_bankroll)
    max_exposure = bankroll * max_exposure_fraction
    current_exposure = sum(float(r.get("stake", "0") or 0.0) for r in open_rows)

    good = sorted(candidates, key=lambda x: x.smart_score, reverse=True)

    selected: List[CandidateBet] = []
    for c in good:
        if open_count >= max_open:
            break
        if current_exposure + c.stake > max_exposure:
            continue
        selected.append(c)
        open_count += 1
        current_exposure += c.stake

    # Cap to top 12 for frontend
    return selected[:12]


# -------------------------------------------------------------------
# Analytics
# -------------------------------------------------------------------

def compute_bankroll_from_history(
    rows: List[Dict[str, Any]], starting_bankroll: float
) -> float:
    if not rows:
        return starting_bankroll

    def parse_ts(r: Dict[str, Any]) -> datetime:
        ts = r.get("timestamp", "")
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return datetime.min

    bankroll = starting_bankroll
    for r in sorted(rows, key=parse_ts):
        status = r.get("status", "")
        result = r.get("result", "")
        if status != "CLOSED" or result not in ("WIN", "LOSS", "PUSH"):
            continue
        profit = float(r.get("profit", "0") or 0.0)
        bankroll += profit
    return bankroll


def compute_analytics(
    rows: List[Dict[str, Any]], starting_bankroll: float
) -> Dict[str, Any]:
    if not rows:
        return {
            "bankroll": starting_bankroll,
            "total_bets": 0,
            "wins": 0,
            "losses": 0,
            "pushes": 0,
            "roi": 0.0,
            "by_sport": {},
            "streaks": {"current": 0, "max_win": 0, "max_loss": 0},
        }

    bankroll = compute_bankroll_from_history(rows, starting_bankroll)
    closed = [r for r in rows if r.get("status") == "CLOSED"]

    wins = sum(1 for r in closed if r.get("result") == "WIN")
    losses = sum(1 for r in closed if r.get("result") == "LOSS")
    pushes = sum(1 for r in closed if r.get("result") == "PUSH")
    total_bets = len(closed)

    total_staked = sum(float(r.get("stake", "0") or 0.0) for r in closed)
    total_profit = sum(float(r.get("profit", "0") or 0.0) for r in closed)
    roi = (total_profit / total_staked) if total_staked > 0 else 0.0

    by_sport: Dict[str, Dict[str, Any]] = {}
    for r in closed:
        sport = r.get("sport", "unknown")
        d = by_sport.setdefault(
            sport,
            {"wins": 0, "losses": 0, "pushes": 0, "profit": 0.0, "bets": 0},
        )
        d["bets"] += 1
        res = r.get("result")
        if res == "WIN":
            d["wins"] += 1
        elif res == "LOSS":
            d["losses"] += 1
        elif res == "PUSH":
            d["pushes"] += 1
        d["profit"] += float(r.get("profit", "0") or 0.0)

    # Streaks
    current_streak = 0
    max_win = 0
    max_loss = 0

    def parse_ts(r: Dict[str, Any]) -> datetime:
        ts = r.get("timestamp", "")
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return datetime.min

    for r in sorted(closed, key=parse_ts):
        res = r.get("result")
        if res == "WIN":
            current_streak = current_streak + 1 if current_streak >= 0 else 1
        elif res == "LOSS":
            current_streak = current_streak - 1 if current_streak <= 0 else -1
        else:
            continue

        if current_streak > 0:
            max_win = max(max_win, current_streak)
        elif current_streak < 0:
            max_loss = min(max_loss, current_streak)

    return {
        "bankroll": bankroll,
        "total_bets": total_bets,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "roi": roi,
        "by_sport": by_sport,
        "streaks": {"current": current_streak, "max_win": max_win, "max_loss": max_loss},
    }


# -------------------------------------------------------------------
# JSON output
# -------------------------------------------------------------------

def build_data_json(
    history_rows: List[Dict[str, Any]],
    analytics: Dict[str, Any],
) -> Dict[str, Any]:
    # Frontend-focused payload
    bankroll = analytics.get("bankroll", 0.0)
    now_str = ts_now_utc().strftime("%Y-%m-%d %H:%M:%S UTC")

    open_rows = [r for r in history_rows if r.get("status") == "OPEN"]

    open_bets = []
    for r in open_rows:
        # map to UI expected keys
        try:
            event_time = datetime.fromisoformat(
                (r.get("event_time") or "").replace("Z", "+00:00")
            )
        except Exception:
            event_time = ts_now_utc()
        local_event_time = utc_to_local_mst(event_time)

        open_bets.append(
            {
                "timestamp": r.get("timestamp", ""),
                "sport": r.get("sport", ""),
                "event": r.get("match", ""),
                "market": r.get("market", ""),
                "team": r.get("team", ""),
                "line": str(r.get("line", "")),
                "odds": str(r.get("odds", "")),
                "bet_amount": str(r.get("stake", "")),
                "status": r.get("status", ""),
                "result": r.get("result", ""),
                "pnl": str(r.get("profit", "")),
                "event_time": local_event_time.strftime("%Y-%m-%d %H:%M"),
            }
        )

    return {
        "bankroll": bankroll,
        "last_updated": now_str,

        # The key the frontend actually expects:
        "picks": open_bets,
        "generated": open_bets,

        # Legacy + canonical:
        "open_bets": open_bets,
        "history": history_rows,
        "analytics": analytics,
    }



# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

# -------------------------------------------------------------------
# Manual Grading Utilities
# -------------------------------------------------------------------

def apply_grade_to_bet(history_rows: List[Dict[str, Any]],
                       bet_id: str,
                       outcome: str,
                       starting_bankroll: float) -> bool:
    """
    Grades a specific bet in history_rows.
    outcome must be 'win', 'loss', or 'push'.
    Returns True if updated, False otherwise.
    """

    outcome = outcome.lower().strip()
    if outcome not in ("win", "loss", "push"):
        print(f"[ERROR] Invalid outcome: {outcome}")
        return False

    for row in history_rows:
        if row.get("bet_id") == bet_id:
            if row.get("status") == "CLOSED":
                print(f"[WARN] Bet {bet_id} already closed.")
                return False

            odds = int(row.get("odds", "0"))
            stake = float(row.get("stake", "0"))

            # Profit calculation
            if outcome == "win":
                profit = round(stake * american_to_decimal(odds) - stake, 2)
            elif outcome == "loss":
                profit = -stake
            else:  # push
                profit = 0.0

            row["status"] = "CLOSED"
            row["result"] = outcome.upper()
            row["profit"] = str(profit)
            row["result_timestamp"] = ts_now_utc().isoformat()

            print(f"[INFO] Bet {bet_id} graded as {outcome.upper()} (profit {profit:+.2f})")
            return True

    print(f"[ERROR] Bet ID not found: {bet_id}")
    return False


def grade_latest_open_bet(history_rows: List[Dict[str, Any]],
                          outcome: str,
                          starting_bankroll: float) -> Optional[str]:
    """Grades the most recent OPEN bet."""
    open_bets = [r for r in history_rows if r.get("status") == "OPEN"]
    if not open_bets:
        print("[WARN] No open bets to grade.")
        return None

    latest = sorted(open_bets, key=lambda r: r["timestamp"], reverse=True)[0]
    bet_id = latest["bet_id"]

    updated = apply_grade_to_bet(history_rows, bet_id, outcome, starting_bankroll)
    if updated:
        return bet_id
    return None



def main() -> None:
    config = Config.load(DEFAULT_CONFIG_PATH)

    history_rows = load_bet_history(config.bet_history_path)
        # Auto-grade any resolvable open bets using live scores
    auto_grade_from_scores(config, history_rows)


    # For now, we are not auto-resolving pending bets via scores to keep it stable.
    # (Your previous version did some of this; we can add it back carefully later.)

    # Compute analytics before adding new bets
    analytics_before = compute_analytics(history_rows, config.starting_bankroll)
    print(
        f"[INFO] Loaded {len(history_rows)} history rows. Bankroll={analytics_before['bankroll']:.2f}"
    )

    # Build & filter candidates
    all_candidates = build_candidates_from_odds(config, history_rows)
    selected = filter_candidates(all_candidates, history_rows, config)
    print(f"[INFO] Selected {len(selected)} new candidate bets.")

    # Append selected bets to history as OPEN
    now_utc = ts_now_utc()
    for cand in selected:
        bet_id = f"{int(now_utc.timestamp() * 1000)}_{cand.event_id}_{cand.market}_{cand.team}"
        ts_str = now_utc.isoformat()
        local_date = utc_to_local_mst(now_utc).strftime("%Y-%m-%d")

        history_rows.append(
            {
                "bet_id": bet_id,
                "event_id": cand.event_id,
                "timestamp": ts_str,
                "date": local_date,
                "sport": cand.sport,
                "match": cand.match,
                "team": cand.team,
                "market": cand.market,
                "line": "" if cand.line is None else str(cand.line),
                "odds": str(cand.odds),
                "stake": f"{cand.stake:.2f}",
                "event_time": cand.event_time_utc.isoformat(),
                "status": "OPEN",
                "result": "",
                "profit": "0.0",
                "result_timestamp": "",
                "bankroll_after": "",
            }
        )

    # Recompute analytics after "placing" bets
    analytics = compute_analytics(history_rows, config.starting_bankroll)

    # Save bet_history
    save_bet_history(history_rows, config.bet_history_path)
    print(
        f"[INFO] Saved {len(history_rows)} history rows to {config.bet_history_path}. "
        f"Bankroll={analytics['bankroll']:.2f}"
    )

    # Build & write data.json
    data_payload = build_data_json(history_rows, analytics)
    out_path = SCRIPT_DIR / config.data_output_path
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(data_payload, f, indent=2)
    print(f"[INFO] Wrote data JSON to {out_path}")


# -------------------------------------------------------------------
# Manual Grading Utilities
# -------------------------------------------------------------------

def apply_grade_to_bet(history_rows: List[Dict[str, Any]],
                       bet_id: str,
                       outcome: str,
                       starting_bankroll: float) -> bool:
    """
    Grades a specific bet in history_rows.
    outcome must be 'win', 'loss', or 'push'.
    Returns True if updated, False otherwise.
    """

    outcome = outcome.lower().strip()
    if outcome not in ("win", "loss", "push"):
        print(f"[ERROR] Invalid outcome: {outcome}")
        return False

    for row in history_rows:
        if row.get("bet_id") == bet_id:
            if row.get("status") == "CLOSED":
                print(f"[WARN] Bet {bet_id} already closed.")
                return False

            odds = int(row.get("odds", "0"))
            stake = float(row.get("stake", "0"))

            # Profit calculation
            if outcome == "win":
                profit = round(stake * american_to_decimal(odds) - stake, 2)
            elif outcome == "loss":
                profit = -stake
            else:  # push
                profit = 0.0

            row["status"] = "CLOSED"
            row["result"] = outcome.upper()
            row["profit"] = str(profit)
            row["result_timestamp"] = ts_now_utc().isoformat()

            print(f"[INFO] Bet {bet_id} graded as {outcome.upper()} (profit {profit:+.2f})")
            return True

    print(f"[ERROR] Bet ID not found: {bet_id}")
    return False


def grade_latest_open_bet(history_rows: List[Dict[str, Any]],
                          outcome: str,
                          starting_bankroll: float) -> Optional[str]:
    """Grades the most recent OPEN bet."""
    open_bets = [r for r in history_rows if r.get("status") == "OPEN"]
    if not open_bets:
        print("[WARN] No open bets to grade.")
        return None

    latest = sorted(open_bets, key=lambda r: r["timestamp"], reverse=True)[0]
    bet_id = latest["bet_id"]

    updated = apply_grade_to_bet(history_rows, bet_id, outcome, starting_bankroll)
    if updated:
        return bet_id
    return None

