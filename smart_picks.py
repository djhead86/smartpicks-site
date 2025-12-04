#!/usr/bin/env python3
"""
SmartPicks v3 – Full version with:

- Multi-sport odds fetch (The Odds API)
- Event-level deduplication (no new bets on already-bet events)
- Rich bet_history.csv schema with automatic migration
- Full grading for H2H, spreads, and totals
- Analytics: ROI, winrate, per-sport stats, streaks, bankroll curve
- Parlay builder from top picks
- JSON output: { generated, picks[], history[], analytics{} }

Config:
- Expects config.json in same directory, or uses sane defaults.
- ODDS_API_KEY taken from environment or config.json.

Author: ChatGPT + Daniel’s brain
"""

import csv
import json
import math
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# ---------------------------
# Paths & config
# ---------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "config.json"

BET_HISTORY_COLUMNS = [
    "bet_id",
    "event_id",
    "timestamp",
    "date",
    "sport",
    "match",
    "team",
    "market",
    "line",
    "odds",
    "stake",
    "event_time",
    "status",
    "result",
    "profit",
    "result_timestamp",
    "bankroll_after",
]

TIMEZONE_OFFSET_HOURS = -7  # MST (no DST) for display; internal is UTC


# ---------------------------
# Data models
# ---------------------------

@dataclass
class Config:
    starting_bankroll: float = 200.0
    sports: List[str] = None
    bet_history_path: str = "bet_history.csv"
    data_output_path: str = "data.json"
    risk_rules: Dict[str, Any] = None
    odds_api_key: str = ""
    days_from_scores: int = 3

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

        sports = data.get(
            "sports",
            ["basketball_nba", "americanfootball_nfl", "soccer_epl"],
        )
        risk_rules = data.get(
            "risk_rules",
            {
                "unit_size": 2.0,
                "max_open_bets": 20,
                "min_ev": 0.01,
                "max_exposure_fraction": 0.10,
            },
        )
        odds_api_key = os.getenv("ODDS_API_KEY") or data.get("odds_api_key", "")

        if not odds_api_key:
            print(
                "[WARN] No ODDS_API_KEY provided. Set env ODDS_API_KEY or config.json['odds_api_key'].",
                file=sys.stderr,
            )

        return cls(
            starting_bankroll=float(data.get("starting_bankroll", 200.0)),
            sports=sports,
            bet_history_path=data.get("bet_history_path", "bet_history.csv"),
            data_output_path=data.get("data_output_path", "data.json"),
            risk_rules=risk_rules,
            odds_api_key=odds_api_key,
            days_from_scores=int(data.get("days_from_scores", 3)),
        )


@dataclass
class CandidateBet:
    event_id: str
    sport: str
    match: str
    team: str
    market: str  # h2h, spreads, totals
    line: Optional[float]
    odds: int
    stake: float
    event_time_utc: datetime
    book: str
    implied_prob: float
    model_prob: float
    edge: float
    smart_score: float

    def to_pick_payload(self) -> Dict[str, Any]:
        # For JSON output (picks[])
        local_time = self.event_time_utc + timedelta(hours=TIMEZONE_OFFSET_HOURS)
        return {
            "event_id": self.event_id,
            "sport": self.sport,
            "match": self.match,
            "team": self.team,
            "market": self.market,
            "line": self.line,
            "odds": self.odds,
            "stake": self.stake,
            "event_time": self.event_time_utc.isoformat() + "Z",
            "event_time_local": local_time.strftime("%Y-%m-%d %H:%M:%S"),
            "book": self.book,
            "implied_prob": round(self.implied_prob, 4),
            "model_prob": round(self.model_prob, 4),
            "edge": round(self.edge, 4),
            "smart_score": round(self.smart_score, 1),
        }


# ---------------------------
# Utility functions
# ---------------------------

def american_to_decimal(odds: int) -> float:
    if odds > 0:
        return 1.0 + odds / 100.0
    else:
        return 1.0 + 100.0 / abs(odds)


def implied_probability(odds: int) -> float:
    if odds > 0:
        return 100.0 / (odds + 100.0)
    else:
        return abs(odds) / (abs(odds) + 100.0)


def compute_profit(stake: float, odds: int, outcome: str) -> float:
    if outcome == "PUSH":
        return 0.0
    if outcome == "LOSS":
        return -stake
    if outcome != "WIN":
        return 0.0
    dec = american_to_decimal(odds)
    return stake * (dec - 1.0)


def ts_now_utc() -> datetime:
    return datetime.now(timezone.utc)


def ts_iso_z(dt: Optional[datetime] = None) -> str:
    if dt is None:
        dt = ts_now_utc()
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def make_bet_id(event_id: str, market: str, line: Optional[float], team: str) -> str:
    line_str = "" if line is None else str(line)
    raw = f"{event_id}_{market}_{line_str}_{team}".lower().replace(" ", "_")
    return re.sub(r"[^a-z0-9_]+", "", raw)


# ---------------------------
# bet_history handling & migration
# ---------------------------

def ensure_bet_history_schema(path: Path) -> List[Dict[str, Any]]:
    """
    Load bet_history.csv and transparently migrate it to the new schema.

    - Adds: event_id, line, result_timestamp if missing.
    - Keeps existing data.
    - Returns list of dict rows with unified schema.
    """
    rows: List[Dict[str, Any]] = []

    if not path.exists():
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=BET_HISTORY_COLUMNS)
            writer.writeheader()
        return []

    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        old_fieldnames = reader.fieldnames or []
        for row in reader:
            rows.append(row)

    if set(old_fieldnames) == set(BET_HISTORY_COLUMNS):
        # Already in good shape
        return rows

    migrated_rows: List[Dict[str, Any]] = []
    for row in rows:
        new_row = {col: "" for col in BET_HISTORY_COLUMNS}

        # Copy what we know
        new_row["bet_id"] = row.get("bet_id", "")
        new_row["timestamp"] = row.get("timestamp", "")
        new_row["date"] = row.get("date", "")
        new_row["sport"] = row.get("sport", "")
        new_row["match"] = row.get("match", "")
        new_row["team"] = row.get("team", "")
        new_row["market"] = row.get("market", "")
        new_row["odds"] = row.get("odds", "")
        new_row["stake"] = row.get("stake", "")
        new_row["event_time"] = row.get("event_time", "")
        new_row["status"] = row.get("status", "")
        new_row["result"] = row.get("result", "")
        new_row["profit"] = row.get("profit", "")
        new_row["bankroll_after"] = row.get("bankroll_after", "")

        # Newer fields
        event_id = row.get("event_id")
        if not event_id:
            event_id = f"legacy_{row.get('sport','')}_{row.get('match','')}"
        new_row["event_id"] = event_id

        new_row["line"] = row.get("line", "")
        new_row["result_timestamp"] = row.get("result_timestamp", "")

        migrated_rows.append(new_row)

    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=BET_HISTORY_COLUMNS)
        writer.writeheader()
        writer.writerows(migrated_rows)

    return migrated_rows


def load_bet_history(path: Path) -> List[Dict[str, Any]]:
    return ensure_bet_history_schema(path)


def append_bet_to_history(path: Path, bet: CandidateBet, bankroll_after: float) -> None:
    rows = load_bet_history(path)
    now = ts_now_utc()
    now_iso = ts_iso_z(now)
    date_str = now.astimezone(timezone(timedelta(hours=TIMEZONE_OFFSET_HOURS))).strftime(
        "%m/%d/%y"
    )

    line_str = "" if bet.line is None else str(bet.line)

    row = {
        "bet_id": make_bet_id(bet.event_id, bet.market, bet.line, bet.team),
        "event_id": bet.event_id,
        "timestamp": now_iso,
        "date": date_str,
        "sport": bet.sport,
        "match": bet.match,
        "team": bet.team,
        "market": bet.market,
        "line": line_str,
        "odds": str(bet.odds),
        "stake": f"{bet.stake:.2f}",
        "event_time": bet.event_time_utc.isoformat().replace("+00:00", "Z"),
        "status": "OPEN",
        "result": "PENDING",
        "profit": "0.0",
        "result_timestamp": "",
        "bankroll_after": f"{bankroll_after:.2f}",
    }

    rows.append(row)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=BET_HISTORY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------
# Odds & scores fetch
# ---------------------------

ODDS_BASE_URL = "https://api.the-odds-api.com/v4"


def http_get(url: str, params: Dict[str, Any]) -> Any:
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[HTTP] Error fetching {url}: {e}", file=sys.stderr)
        return []


def fetch_odds_for_sport(sport: str, api_key: str) -> List[Dict[str, Any]]:
    url = f"{ODDS_BASE_URL}/sports/{sport}/odds"
    params = {
        "apiKey": api_key,
        "regions": "us",
        "markets": "h2h,spreads,totals",
        "oddsFormat": "american",
    }
    print(f"[ODDS] GET {url}")
    return http_get(url, params)


def fetch_scores_for_sport(sport: str, api_key: str, days_from: int) -> List[Dict[str, Any]]:
    url = f"{ODDS_BASE_URL}/sports/{sport}/scores"
    params = {
        "apiKey": api_key,
        "daysFrom": str(days_from),
    }
    print(f"[SCORES] GET {url}")
    return http_get(url, params)


def build_scores_index(
    sports: List[str], api_key: str, days_from: int
) -> Dict[str, Dict[str, Any]]:
    by_event: Dict[str, Dict[str, Any]] = {}
    for sport in sports:
        scores = fetch_scores_for_sport(sport, api_key, days_from)
        for game in scores or []:
            event_id = game.get("id")
            if not event_id:
                continue
            by_event[event_id] = game
    return by_event


# ---------------------------
# Bet grading
# ---------------------------

def grade_single_bet(bet_row: Dict[str, Any], score: Dict[str, Any]) -> str:
    """
    Return outcome: 'WIN', 'LOSS', 'PUSH', or 'PENDING'
    """
    market = bet_row.get("market", "")
    team = bet_row.get("team", "")
    line_str = bet_row.get("line", "")
    line = None
    if line_str not in ("", None):
        try:
            line = float(line_str)
        except ValueError:
            line = None

    scores = score.get("scores") or []
    home_score = away_score = None
    for s in scores:
        if s.get("name") == "home":
            home_score = int(s.get("score", 0))
        elif s.get("name") == "away":
            away_score = int(s.get("score", 0))

    if home_score is None or away_score is None:
        return "PENDING"

    total_points = home_score + away_score
    home_team = score.get("home_team")
    away_team = score.get("away_team")

    if market == "h2h":
        winner = score.get("winner")
        if not winner:
            if home_score > away_score:
                winner = home_team
            elif away_score > home_score:
                winner = away_team
            else:
                return "PUSH"
        if team == winner:
            return "WIN"
        else:
            return "LOSS"

    if market == "spreads" and line is not None:
        if team == home_team:
            margin = home_score - away_score
        elif team == away_team:
            margin = away_score - home_score
        else:
            return "PENDING"
        adjusted = margin + line
        if adjusted > 0:
            return "WIN"
        elif adjusted == 0:
            return "PUSH"
        else:
            return "LOSS"

    if market == "totals" and line is not None:
        lt = team.lower()
        if "over" in lt:
            if total_points > line:
                return "WIN"
            elif total_points == line:
                return "PUSH"
            else:
                return "LOSS"
        if "under" in lt:
            if total_points < line:
                return "WIN"
            elif total_points == line:
                return "PUSH"
            else:
                return "LOSS"

    return "PENDING"


def grade_open_bets(
    path: Path,
    scores_by_event_id: Dict[str, Dict[str, Any]],
    starting_bankroll: float,
) -> List[Dict[str, Any]]:
    rows = load_bet_history(path)
    if not rows:
        return rows

    def parse_ts(r: Dict[str, Any]) -> datetime:
        ts = r.get("timestamp", "")
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return datetime.min

    rows_sorted = sorted(rows, key=parse_ts)
    bankroll = starting_bankroll

    for r in rows_sorted:
        stake = float(r.get("stake", "0") or 0.0)
        odds = int(float(r.get("odds", "0") or 0.0))
        status = r.get("status", "")
        result = r.get("result", "")
        event_id = r.get("event_id", "")

        # Already graded: recompute bankroll from stored profit
        if status != "OPEN" and result in ("WIN", "LOSS", "PUSH"):
            profit = float(r.get("profit", "0") or 0.0)
            bankroll += profit
            r["bankroll_after"] = f"{bankroll:.2f}"
            continue

        # Need to try grading
        score = scores_by_event_id.get(event_id)
        if not score or not score.get("completed"):
            r["bankroll_after"] = f"{bankroll:.2f}"
            continue

        outcome = grade_single_bet(r, score)
        if outcome == "PENDING":
            r["bankroll_after"] = f"{bankroll:.2f}"
            continue

        r["result"] = outcome
        r["status"] = "CLOSED"
        profit = compute_profit(stake, odds, outcome)
        bankroll += profit
        r["profit"] = f"{profit:.2f}"
        r["result_timestamp"] = ts_iso_z()
        r["bankroll_after"] = f"{bankroll:.2f}"

    # Write back
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=BET_HISTORY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows_sorted)

    return rows_sorted


# ---------------------------
# Candidate building & risk
# ---------------------------

def naive_model_probability(impl_prob: float, market: str, sport: str) -> float:
    """
    Quick-and-dirty "model probability":
    - Slight bias toward favorites (impl_prob > 0.5) to emulate sharp tilt
    - Slight bias against huge dogs
    This is intentionally simple; true model can replace this later.
    """
    if impl_prob > 0.5:
        return min(impl_prob * 1.03, 0.99)
    else:
        return max(impl_prob * 0.97, 0.01)


def compute_edge(impl_prob: float, model_prob: float, odds: int) -> float:
    """
    Expected value edge vs implied, using model probability and decimal odds.
    EV = p * (decimal-1) - (1-p)
    """
    dec = american_to_decimal(odds)
    ev = model_prob * (dec - 1.0) - (1.0 - model_prob)
    return ev


def compute_smart_score(edge: float, model_prob: float, odds: int) -> float:
    """
    Convert EV + confidence into a 0-100 "Smart Score".
    Very rough scaling:
    - edge in [-0.1, 0.2] mapped to 0-100 with mild emphasis on high edge & decent probability.
    """
    base = (edge + 0.1) / 0.3  # normalize roughly [-0.1,0.2] to [0,1]
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

    # Build set of event_ids that already have OPEN bets (event-level dedup)
    open_event_ids = {
        r.get("event_id")
        for r in history_rows
        if r.get("status") == "OPEN" and r.get("event_id")
    }

    candidates: List[CandidateBet] = []

    for sport in config.sports:
        odds_json = fetch_odds_for_sport(sport, api_key)
        for game in odds_json or []:
            event_id = game.get("id")
            if not event_id:
                continue

            # Event-level dedup: if we've ever bet this event and it's still open, skip
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

            bookmakers = game.get("bookmakers") or []
            # Build best lines by market/outcome
            best_by_market: Dict[Tuple[str, str], Tuple[int, str, Optional[float]]] = {}
            # key: (market, outcome_key) → (odds, book, line)

            for bm in bookmakers:
                book = bm.get("title", "Unknown")
                for mk in bm.get("markets") or []:
                    market_key = mk.get("key")
                    outcomes = mk.get("outcomes") or []
                    for o in outcomes:
                        name = o.get("name")
                        price = int(o.get("price", 0))
                        point = o.get("point")
                        line_val: Optional[float] = None
                        if point not in (None, ""):
                            try:
                                line_val = float(point)
                            except ValueError:
                                line_val = None

                        if market_key == "h2h":
                            # outcome key is team name
                            outcome_key = name
                        elif market_key == "spreads":
                            outcome_key = name  # team
                        elif market_key == "totals":
                            outcome_key = name.lower()  # "Over"/"Under"
                        else:
                            continue

                        key = (market_key, outcome_key)
                        # We want "best" odds = highest absolute EV for now → simply highest decimal
                        current = best_by_market.get(key)
                        if current is None:
                            best_by_market[key] = (price, book, line_val)
                        else:
                            cur_price, _, _ = current
                            if american_to_decimal(price) > american_to_decimal(cur_price):
                                best_by_market[key] = (price, book, line_val)

            # Convert best_by_market to candidate list
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
                    team = outcome_key  # "Over" or "Under"
                    market = "totals"
                else:
                    continue

                impl_prob = implied_probability(odds)
                model_prob = naive_model_probability(impl_prob, market, sport)
                edge = compute_edge(impl_prob, model_prob, odds)
                smart_score = compute_smart_score(edge, model_prob, odds)

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
    min_ev = float(config.risk_rules.get("min_ev", 0.01))
    max_open = int(config.risk_rules.get("max_open_bets", 20))
    max_exposure_fraction = float(config.risk_rules.get("max_exposure_fraction", 0.10))

    open_rows = [r for r in history_rows if r.get("status") == "OPEN"]
    open_count = len(open_rows)
    bankroll = compute_bankroll_from_history(history_rows, config.starting_bankroll)
    max_exposure = bankroll * max_exposure_fraction
    current_exposure = sum(float(r.get("stake", "0") or 0.0) for r in open_rows)

    # Filter by EV
    good = [c for c in candidates if c.edge >= min_ev]

    # Sort by Smart Score descending
    good.sort(key=lambda x: x.smart_score, reverse=True)

    selected: List[CandidateBet] = []
    for c in good:
        if open_count >= max_open:
            break
        if current_exposure + c.stake > max_exposure:
            continue
        selected.append(c)
        open_count += 1
        current_exposure += c.stake

    # Limit to a nice top N (e.g., 12)
    return selected[:12]


# ---------------------------
# Analytics
# ---------------------------

def compute_bankroll_from_history(
    rows: List[Dict[str, Any]], starting_bankroll: float
) -> float:
    if not rows:
        return starting_bankroll
    # We recompute from start to avoid drift
    bankroll = starting_bankroll
    # Sort by timestamp
    def parse_ts(r: Dict[str, Any]) -> datetime:
        ts = r.get("timestamp", "")
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return datetime.min

    for r in sorted(rows, key=parse_ts):
        status = r.get("status", "")
        result = r.get("result", "")
        if status != "CLOSED" or result not in ("WIN", "LOSS", "PUSH"):
            continue
        profit = float(r.get("profit", "0") or 0.0)
        bankroll += profit
    return bankroll


def compute_analytics(rows: List[Dict[str, Any]], starting_bankroll: float) -> Dict[str, Any]:
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
            "parlays": [],
        }

    # Chronological
    def parse_ts(r: Dict[str, Any]) -> datetime:
        ts = r.get("timestamp", "")
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return datetime.min

    rows_sorted = sorted(rows, key=parse_ts)
    bankroll = starting_bankroll

    total_bets = 0
    wins = losses = pushes = 0
    total_staked = 0.0
    by_sport: Dict[str, Dict[str, Any]] = {}

    current_streak = 0
    max_win_streak = 0
    max_loss_streak = 0
    last_streak_type: Optional[str] = None  # "WIN" or "LOSS"

    for r in rows_sorted:
        status = r.get("status", "")
        result = r.get("result", "")
        sport = r.get("sport", "")

        if status != "CLOSED" or result not in ("WIN", "LOSS", "PUSH"):
            continue

        total_bets += 1
        stake = float(r.get("stake", "0") or 0.0)
        profit = float(r.get("profit", "0") or 0.0)
        total_staked += stake
        bankroll += profit

        if sport not in by_sport:
            by_sport[sport] = {
                "bets": 0,
                "wins": 0,
                "losses": 0,
                "pushes": 0,
                "staked": 0.0,
                "profit": 0.0,
                "roi": 0.0,
            }

        s = by_sport[sport]
        s["bets"] += 1
        s["staked"] += stake
        s["profit"] += profit

        if result == "WIN":
            wins += 1
            s["wins"] += 1
            # streak
            if last_streak_type == "WIN":
                current_streak += 1
            else:
                current_streak = 1
                last_streak_type = "WIN"
            max_win_streak = max(max_win_streak, current_streak)
        elif result == "LOSS":
            losses += 1
            s["losses"] += 1
            if last_streak_type == "LOSS":
                current_streak += 1
            else:
                current_streak = 1
                last_streak_type = "LOSS"
            max_loss_streak = max(max_loss_streak, current_streak)
        elif result == "PUSH":
            pushes += 1
            s["pushes"] += 1

    overall_roi = (bankroll - starting_bankroll) / total_staked if total_staked > 0 else 0.0

    for sport, s in by_sport.items():
        if s["staked"] > 0:
            s["roi"] = s["profit"] / s["staked"]
        else:
            s["roi"] = 0.0

    analytics = {
        "bankroll": round(bankroll, 2),
        "total_bets": total_bets,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "roi": round(overall_roi, 4),
        "by_sport": by_sport,
        "streaks": {
            "current": current_streak,
            "max_win": max_win_streak,
            "max_loss": max_loss_streak,
        },
        "parlays": [],  # filled later
    }

    return analytics


# ---------------------------
# Parlay builder
# ---------------------------

def build_parlays_from_picks(picks: List[CandidateBet]) -> List[Dict[str, Any]]:
    """
    Simple parlay builder:
    - Up to one pick per event
    - Top 3–4 Smart Score legs
    """
    if not picks:
        return []

    # Unique by event_id
    seen_events = set()
    unique_picks: List[CandidateBet] = []
    for p in sorted(picks, key=lambda x: x.smart_score, reverse=True):
        if p.event_id in seen_events:
            continue
        seen_events.add(p.event_id)
        unique_picks.append(p)

    legs = unique_picks[:4]  # up to 4-leg parlay
    if len(legs) < 2:
        return []

    total_dec = 1.0
    approx_p = 1.0
    for leg in legs:
        total_dec *= american_to_decimal(leg.odds)
        approx_p *= leg.model_prob

    implied_ev = approx_p * (total_dec - 1.0) - (1.0 - approx_p)

    parlay = {
        "legs": [leg.to_pick_payload() for leg in legs],
        "combined_decimal_odds": round(total_dec, 3),
        "approx_win_prob": round(approx_p, 4),
        "approx_ev": round(implied_ev, 4),
    }

    return [parlay]


# ---------------------------
# Main orchestration
# ---------------------------

def main() -> None:
    config = Config.load(DEFAULT_CONFIG_PATH)
    bet_history_path = (SCRIPT_DIR / config.bet_history_path).resolve()
    data_output_path = (SCRIPT_DIR / config.data_output_path).resolve()

    print(f"[INFO] bet_history: {bet_history_path}")
    print(f"[INFO] data.json  : {data_output_path}")

    # 1) Grade existing bets using scores
    scores_by_event = build_scores_index(
        config.sports, config.odds_api_key, config.days_from_scores
    )
    graded_history = grade_open_bets(
        bet_history_path, scores_by_event, config.starting_bankroll
    )

    # Reload history (now graded)
    history_rows = load_bet_history(bet_history_path)

    # 2) Build new candidates from odds, apply risk/dedup
    all_candidates = build_candidates_from_odds(config, history_rows)
    picks = filter_candidates(all_candidates, history_rows, config)

    # 3) Append picks to bet_history, updating bankroll as we go
    bankroll = compute_bankroll_from_history(history_rows, config.starting_bankroll)
    for pick in picks:
        bankroll_after = bankroll + 0.0  # bankroll doesn't change until graded
        append_bet_to_history(bet_history_path, pick, bankroll_after)

    # Reload including newly added picks
    history_rows = load_bet_history(bet_history_path)

    # 4) Compute analytics
    analytics = compute_analytics(history_rows, config.starting_bankroll)

    # 5) Build parlay suggestions from newly selected picks
    parlays = build_parlays_from_picks(picks)
    analytics["parlays"] = parlays

    # 6) JSON payload: { generated, picks[], history[], analytics{} }
    payload = {
        "generated": ts_iso_z(),
        "picks": [p.to_pick_payload() for p in picks],
        "history": history_rows,
        "analytics": analytics,
    }

    data_output_path.parent.mkdir(parents=True, exist_ok=True)
    with data_output_path.open("w") as f:
        json.dump(payload, f, indent=2)

    print(
        f"[DONE] Generated {len(picks)} picks, "
        f"{len(history_rows)} history rows. Bankroll={analytics['bankroll']:.2f}"
    )


if __name__ == "__main__":
    main()
