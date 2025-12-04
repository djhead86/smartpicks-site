#!/usr/bin/env python3
"""
SmartPicks - Sports Betting Analytics Engine
Fetches odds, calculates EV, generates picks, grades results
"""

import json
import csv
import requests
import time
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

# ============================================================================
# CONFIGURATION
# ============================================================================

CONFIG_FILE = "config.json"
DATA_OUTPUT = "data.json"
SCORES_OUTPUT = "scores.json"
BET_HISTORY = "bet_history.csv"

# Sport mappings
SPORT_KEYS = {
    "nba": "basketball_nba",
    "nfl": "americanfootball_nfl",
    "nhl": "icehockey_nhl",
    "epl": "soccer_epl",
    "uefa": "soccer_uefa_champions_league",
    "ufc": "mma_mixed_martial_arts"
}

SPORT_NAMES = {
    "basketball_nba": "NBA",
    "americanfootball_nfl": "NFL",
    "icehockey_nhl": "NHL",
    "soccer_epl": "EPL",
    "soccer_uefa_champions_league": "UEFA",
    "mma_mixed_martial_arts": "UFC"
}

# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class Config:
    api_key: str
    backup_api_key: Optional[str]
    base_bankroll: float
    unit_fraction: float
    max_open_bets: int
    thresholds: Dict[str, Optional[float]]
    parlay_legs: int
    sports: List[str]

@dataclass
class Pick:
    sport: str
    event_id: str
    commence_time: str
    home_team: str
    away_team: str
    pick_type: str  # 'h2h', 'spreads', 'totals'
    pick: str  # Team name or Over/Under
    odds: int  # American odds
    fair_prob: float
    market_prob: float
    ev: float
    smart_score: float
    stake: float
    status: str  # 'open', 'pending', 'graded'
    result: Optional[str] = None  # 'WIN', 'LOSS', 'PUSH'
    profit: Optional[float] = None

# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging(debug: bool = False):
    """Configure logging based on debug flag"""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION LOADER
# ============================================================================

def load_config() -> Config:
    """Load configuration from config.json"""
    try:
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
        
        config = Config(
            api_key=data.get('api_key', ''),
            backup_api_key=data.get('backup_api_key'),
            base_bankroll=data.get('base_bankroll', 1000),
            unit_fraction=data.get('unit_fraction', 0.01),
            max_open_bets=data.get('max_open_bets', 20),
            thresholds=data.get('thresholds', {
                'nba': 1.2,
                'nfl': 1.0,
                'nhl': 1.0,
                'epl': 1.0,
                'uefa': 1.0,
                'ufc': None
            }),
            parlay_legs=data.get('parlay_legs', 5),
            sports=data.get('sports', list(SPORT_KEYS.values()))
        )
        
        logger.info(f"✓ Config loaded: Bankroll=${config.base_bankroll}, Unit={config.unit_fraction*100}%")
        return config
    
    except FileNotFoundError:
        logger.error(f"Config file not found: {CONFIG_FILE}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file: {e}")
        raise

# ============================================================================
# ODDS API INTEGRATION
# ============================================================================

def fetch_odds(sport_key: str, api_key: str, retries: int = 3) -> Optional[List[Dict]]:
    """
    Fetch odds from The Odds API with retry logic
    """
    base_url = "https://api.the-odds-api.com/v4/sports"
    url = f"{base_url}/{sport_key}/odds/"
    
    params = {
        'apiKey': api_key,
        'regions': 'us',
        'markets': 'h2h,spreads,totals',
        'oddsFormat': 'american'
    }
    
    for attempt in range(retries):
        try:
            logger.debug(f"Fetching {sport_key} (attempt {attempt + 1}/{retries})")
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"✓ Fetched {len(data)} events for {SPORT_NAMES.get(sport_key, sport_key)}")
            return data
        
        except requests.exceptions.RequestException as e:
            logger.warning(f"API request failed for {sport_key}: {e}")
            if attempt < retries - 1:
                wait_time = 2 ** attempt
                logger.debug(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"✗ Failed to fetch {sport_key} after {retries} attempts")
                return None

def fetch_all_odds(config: Config) -> Dict[str, List[Dict]]:
    """Fetch odds for all configured sports"""
    all_odds = {}
    
    for sport_key in config.sports:
        odds = fetch_odds(sport_key, config.api_key)
        
        # Try backup API key if primary fails
        if odds is None and config.backup_api_key:
            logger.info(f"Trying backup API key for {sport_key}")
            odds = fetch_odds(sport_key, config.backup_api_key)
        
        if odds:
            all_odds[sport_key] = odds
    
    return all_odds

# ============================================================================
# PROBABILITY & EV CALCULATIONS
# ============================================================================

def american_to_prob(odds: int) -> float:
    """Convert American odds to implied probability"""
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)

def calculate_fair_prob(odds: int, vig_removal: float = 0.05) -> float:
    """
    Calculate fair probability with vig removal
    Simple method: boost implied prob by ~5% to remove bookmaker edge
    """
    market_prob = american_to_prob(odds)
    fair_prob = market_prob * (1 + vig_removal)
    return min(fair_prob, 0.99)  # Cap at 99%

def calculate_ev(fair_prob: float, odds: int, stake: float) -> float:
    """
    Calculate Expected Value
    EV = (fair_prob × payout) - (loss_prob × stake)
    """
    market_prob = american_to_prob(odds)
    
    if odds > 0:
        payout = stake * (odds / 100)
    else:
        payout = stake * (100 / abs(odds))
    
    ev = (fair_prob * payout) - ((1 - fair_prob) * stake)
    return ev

def calculate_smart_score(ev: float, fair_prob: float, market_prob: float, 
                         odds: int, sport: str) -> float:
    """
    Calculate Smart Score: 4-factor blend
    1. EV component
    2. Market sharpness (how far odds are from even money)
    3. Probability delta (fair vs market)
    4. Sport weighting
    """
    # Factor 1: EV normalized
    ev_factor = max(0, ev / 10)  # Scale EV to 0-1 range
    
    # Factor 2: Market sharpness (prefer +EV on underdogs or sharp lines)
    sharpness = abs(odds) / 200  # Normalize odds distance from +100
    
    # Factor 3: Probability delta
    prob_delta = abs(fair_prob - market_prob)
    
    # Factor 4: Sport weighting (UFC gets slight boost since moneyline only)
    sport_weight = 1.1 if sport == 'mma_mixed_martial_arts' else 1.0
    
    # Blend factors
    smart_score = (
        ev_factor * 0.4 +
        sharpness * 0.2 +
        prob_delta * 0.3 +
        sport_weight * 0.1
    )
    
    return smart_score

# ============================================================================
# PICK GENERATION
# ============================================================================

def generate_picks(odds_data: Dict[str, List[Dict]], config: Config) -> List[Pick]:
    """Generate all candidate picks from odds data"""
    picks = []
    stake = config.base_bankroll * config.unit_fraction
    
    for sport_key, events in odds_data.items():
        sport_short = get_sport_short_name(sport_key)
        threshold = config.thresholds.get(sport_short)
        
        logger.debug(f"Processing {len(events)} events for {sport_short}")
        
        for event in events:
            event_picks = extract_picks_from_event(
                event, sport_key, sport_short, stake, threshold
            )
            picks.extend(event_picks)
    
    logger.info(f"✓ Generated {len(picks)} candidate picks")
    return picks

def get_sport_short_name(sport_key: str) -> str:
    """Convert API sport key to short name"""
    mapping = {
        'basketball_nba': 'nba',
        'americanfootball_nfl': 'nfl',
        'icehockey_nhl': 'nhl',
        'soccer_epl': 'epl',
        'soccer_uefa_champions_league': 'uefa',
        'mma_mixed_martial_arts': 'ufc'
    }
    return mapping.get(sport_key, sport_key)

def extract_picks_from_event(event: Dict, sport_key: str, sport_short: str, 
                             stake: float, threshold: Optional[float]) -> List[Pick]:
    """Extract all viable picks from a single event"""
    picks = []
    
    event_id = event.get('id', '')
    commence_time = event.get('commence_time', '')
    home_team = event.get('home_team', '')
    away_team = event.get('away_team', '')
    
    bookmakers = event.get('bookmakers', [])
    if not bookmakers:
        return picks
    
    # Use first bookmaker's odds (can be enhanced to compare multiple books)
    book = bookmakers[0]
    markets = book.get('markets', [])
    
    for market in markets:
        market_key = market.get('key', '')
        outcomes = market.get('outcomes', [])
        
        # UFC: Moneyline only
        if sport_short == 'ufc' and market_key != 'h2h':
            continue
        
        for outcome in outcomes:
            pick_name = outcome.get('name', '')
            odds = outcome.get('price', 0)
            
            if odds == 0:
                continue
            
            # Calculate probabilities and EV
            fair_prob = calculate_fair_prob(odds)
            market_prob = american_to_prob(odds)
            ev = calculate_ev(fair_prob, odds, stake)
            smart_score = calculate_smart_score(
                ev, fair_prob, market_prob, odds, sport_key
            )
            
            # Apply threshold filtering
            if threshold is not None and smart_score < threshold:
                continue
            
            # Only positive EV picks
            if ev <= 0:
                continue
            
            pick = Pick(
                sport=sport_short.upper(),
                event_id=event_id,
                commence_time=commence_time,
                home_team=home_team,
                away_team=away_team,
                pick_type=market_key,
                pick=pick_name,
                odds=odds,
                fair_prob=fair_prob,
                market_prob=market_prob,
                ev=ev,
                smart_score=smart_score,
                stake=stake,
                status='open'
            )
            
            picks.append(pick)
    
    return picks

# ============================================================================
# PICK FILTERING & DEDUPLICATION
# ============================================================================

def deduplicate_picks(picks: List[Pick]) -> List[Pick]:
    """Remove duplicate picks for the same event"""
    seen_events = set()
    unique_picks = []
    
    for pick in picks:
        event_key = f"{pick.event_id}_{pick.pick_type}_{pick.pick}"
        if event_key not in seen_events:
            seen_events.add(event_key)
            unique_picks.append(pick)
    
    logger.info(f"✓ Deduplicated: {len(picks)} → {len(unique_picks)} picks")
    return unique_picks

def sort_picks_by_sport(picks: List[Pick]) -> Dict[str, List[Pick]]:
    """Organize picks by sport"""
    by_sport = {
        'NBA': [],
        'NFL': [],
        'NHL': [],
        'EPL': [],
        'UEFA': [],
        'UFC': []
    }
    
    for pick in picks:
        if pick.sport in by_sport:
            by_sport[pick.sport].append(pick)
    
    # Sort each sport by EV descending
    for sport in by_sport:
        by_sport[sport].sort(key=lambda p: p.ev, reverse=True)
    
    return by_sport

# ============================================================================
# PARLAY BUILDER
# ============================================================================

def build_parlay(picks: List[Pick], num_legs: int = 5) -> List[Pick]:
    """Build top N EV parlay from all picks"""
    # Sort all picks by EV globally
    sorted_picks = sorted(picks, key=lambda p: p.ev, reverse=True)
    
    # Take top N
    parlay = sorted_picks[:num_legs]
    
    logger.info(f"✓ Built {len(parlay)}-leg parlay (Total EV: ${sum(p.ev for p in parlay):.2f})")
    return parlay

# ============================================================================
# GRADING ENGINE
# ============================================================================

def fetch_scores(sport_key: str, api_key: str) -> Optional[List[Dict]]:
    """Fetch scores from Odds API"""
    base_url = "https://api.the-odds-api.com/v4/sports"
    url = f"{base_url}/{sport_key}/scores/"
    
    params = {
        'apiKey': api_key,
        'daysFrom': 1
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch scores for {sport_key}: {e}")
        return None

def grade_picks(picks: List[Pick], config: Config) -> List[Pick]:
    """Grade completed picks and update results"""
    graded = []
    
    # Fetch scores for all sports
    all_scores = {}
    for sport_key in config.sports:
        scores = fetch_scores(sport_key, config.api_key)
        if scores:
            all_scores[sport_key] = {s.get('id'): s for s in scores}
    
    for pick in picks:
        # Skip already graded picks
        if pick.status == 'graded':
            graded.append(pick)
            continue
        
        # Find matching score
        sport_key = SPORT_KEYS.get(pick.sport.lower())
        if not sport_key or sport_key not in all_scores:
            graded.append(pick)
            continue
        
        event_score = all_scores[sport_key].get(pick.event_id)
        if not event_score:
            graded.append(pick)
            continue
        
        # Check if completed
        if not event_score.get('completed', False):
            pick.status = 'pending'
            graded.append(pick)
            continue
        
        # Grade the pick
        result = determine_result(pick, event_score)
        pick.result = result
        pick.status = 'graded'
        
        # Calculate profit
        if result == 'WIN':
            if pick.odds > 0:
                pick.profit = pick.stake * (pick.odds / 100)
            else:
                pick.profit = pick.stake * (100 / abs(pick.odds))
        elif result == 'LOSS':
            pick.profit = -pick.stake
        else:  # PUSH
            pick.profit = 0
        
        graded.append(pick)
        logger.info(f"✓ Graded: {pick.sport} {pick.pick} = {result} (${pick.profit:+.2f})")
    
    return graded

def determine_result(pick: Pick, score_data: Dict) -> str:
    """Determine if pick won, lost, or pushed"""
    scores = score_data.get('scores', [])
    if len(scores) < 2:
        return 'PUSH'
    
    home_score = next((s['score'] for s in scores if s['name'] == pick.home_team), None)
    away_score = next((s['score'] for s in scores if s['name'] == pick.away_team), None)
    
    if home_score is None or away_score is None:
        return 'PUSH'
    
    # H2H (Moneyline)
    if pick.pick_type == 'h2h':
        if pick.pick == pick.home_team:
            return 'WIN' if home_score > away_score else 'LOSS' if home_score < away_score else 'PUSH'
        else:
            return 'WIN' if away_score > home_score else 'LOSS' if away_score < home_score else 'PUSH'
    
    # Spreads (simplified - needs point value parsing)
    elif pick.pick_type == 'spreads':
        # This is simplified - real implementation needs spread value
        return 'PUSH'
    
    # Totals (simplified - needs total value parsing)
    elif pick.pick_type == 'totals':
        # This is simplified - real implementation needs total value
        return 'PUSH'
    
    return 'PUSH'

# ============================================================================
# BET HISTORY TRACKING
# ============================================================================

def update_bet_history(picks: List[Pick]):
    """Append graded picks to bet_history.csv"""
    file_exists = Path(BET_HISTORY).exists()
    
    graded_picks = [p for p in picks if p.status == 'graded' and p.result]
    
    if not graded_picks:
        return
    
    with open(BET_HISTORY, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'timestamp', 'sport', 'event_id', 'pick', 'odds', 
            'stake', 'ev', 'smart_score', 'result', 'profit'
        ])
        
        if not file_exists:
            writer.writeheader()
        
        for pick in graded_picks:
            writer.writerow({
                'timestamp': datetime.now().isoformat(),
                'sport': pick.sport,
                'event_id': pick.event_id,
                'pick': pick.pick,
                'odds': pick.odds,
                'stake': pick.stake,
                'ev': round(pick.ev, 2),
                'smart_score': round(pick.smart_score, 2),
                'result': pick.result,
                'profit': round(pick.profit, 2) if pick.profit else 0
            })
    
    total_profit = sum(p.profit for p in graded_picks if p.profit)
    logger.info(f"✓ Updated bet history: {len(graded_picks)} picks, ${total_profit:+.2f} profit")

# ============================================================================
# JSON OUTPUT GENERATION
# ============================================================================

def generate_data_json(picks_by_sport: Dict[str, List[Pick]], 
                       parlay: List[Pick], config: Config):
    """Generate data.json for frontend"""
    
    # Calculate current bankroll from history
    current_bankroll = calculate_current_bankroll(config)
    
    data = {
        'generated_at': datetime.now().isoformat(),
        'bankroll': current_bankroll,
        'open_bets': count_open_bets(picks_by_sport),
        'pick_cards': {},
        'parlay_card': {
            'legs': len(parlay),
            'total_stake': sum(p.stake for p in parlay),
            'total_ev': sum(p.ev for p in parlay),
            'picks': [pick_to_dict(p) for p in parlay]
        }
    }
    
    # Add sport-specific cards
    for sport, picks in picks_by_sport.items():
        if picks:
            data['pick_cards'][sport.lower()] = [pick_to_dict(p) for p in picks[:10]]
    
    with open(DATA_OUTPUT, 'w') as f:
        json.dump(data, f, indent=2)
    
    logger.info(f"✓ Generated {DATA_OUTPUT}")

def generate_scores_json(config: Config):
    """Generate scores.json for live ticker"""
    all_scores = []
    
    for sport_key in config.sports:
        scores = fetch_scores(sport_key, config.api_key)
        if scores:
            for game in scores:
                all_scores.append({
                    'sport': SPORT_NAMES.get(sport_key, sport_key),
                    'home_team': game.get('home_team', ''),
                    'away_team': game.get('away_team', ''),
                    'home_score': get_team_score(game, game.get('home_team')),
                    'away_score': get_team_score(game, game.get('away_team')),
                    'status': 'final' if game.get('completed') else 'live',
                    'commence_time': game.get('commence_time', '')
                })
    
    output = {
        'last_updated': datetime.now().isoformat(),
        'games': all_scores
    }
    
    with open(SCORES_OUTPUT, 'w') as f:
        json.dump(output, f, indent=2)
    
    logger.info(f"✓ Generated {SCORES_OUTPUT} ({len(all_scores)} games)")

def get_team_score(game: Dict, team: str) -> Optional[int]:
    """Extract team score from game data"""
    scores = game.get('scores')
    if not scores:
        return None
    
    for score in scores:
        if score.get('name') == team:
            return score.get('score')
    return None

def pick_to_dict(pick: Pick) -> Dict:
    """Convert Pick to dictionary for JSON"""
    return {
        'sport': pick.sport,
        'event_id': pick.event_id,
        'commence_time': pick.commence_time,
        'matchup': f"{pick.away_team} @ {pick.home_team}",
        'pick_type': pick.pick_type,
        'pick': pick.pick,
        'odds': pick.odds,
        'stake': round(pick.stake, 2),
        'ev': round(pick.ev, 2),
        'smart_score': round(pick.smart_score, 2),
        'status': pick.status,
        'result': pick.result,
        'profit': round(pick.profit, 2) if pick.profit else None
    }

def count_open_bets(picks_by_sport: Dict[str, List[Pick]]) -> int:
    """Count total open bets"""
    count = 0
    for picks in picks_by_sport.values():
        count += sum(1 for p in picks if p.status in ['open', 'pending'])
    return count

def calculate_current_bankroll(config: Config) -> float:
    """Calculate current bankroll from history"""
    if not Path(BET_HISTORY).exists():
        return config.base_bankroll
    
    total_profit = 0
    try:
        with open(BET_HISTORY, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_profit += float(row.get('profit', 0))
    except Exception as e:
        logger.warning(f"Could not calculate bankroll from history: {e}")
        return config.base_bankroll
    
    return config.base_bankroll + total_profit

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution flow"""
    parser = argparse.ArgumentParser(description='SmartPicks Sports Betting Engine')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()
    
    global logger
    logger = setup_logging(args.debug)
    
    logger.info("=" * 60)
    logger.info("SmartPicks Engine Starting")
    logger.info("=" * 60)
    
    try:
        # 1. Load configuration
        config = load_config()
        
        # 2. Fetch odds from API
        logger.info("Fetching odds from API...")
        odds_data = fetch_all_odds(config)
        
        if not odds_data:
            logger.error("No odds data fetched. Exiting.")
            return
        
        # 3. Generate picks
        logger.info("Generating picks...")
        all_picks = generate_picks(odds_data, config)
        
        # 4. Deduplicate
        all_picks = deduplicate_picks(all_picks)
        
        # 5. Grade existing picks
        logger.info("Grading picks...")
        all_picks = grade_picks(all_picks, config)
        
        # 6. Update bet history
        update_bet_history(all_picks)
        
        # 7. Organize by sport
        picks_by_sport = sort_picks_by_sport(all_picks)
        
        # 8. Build parlay
        open_picks = [p for p in all_picks if p.status == 'open']
        parlay = build_parlay(open_picks, config.parlay_legs)
        
        # 9. Generate outputs
        logger.info("Generating output files...")
        generate_data_json(picks_by_sport, parlay, config)
        generate_scores_json(config)
        
        # 10. Summary
        logger.info("=" * 60)
        logger.info(f"✓ SmartPicks Complete")
        logger.info(f"  Total Picks: {len(all_picks)}")
        logger.info(f"  Open: {count_open_bets(picks_by_sport)}")
        logger.info(f"  Parlay Legs: {len(parlay)}")
        logger.info(f"  Bankroll: ${calculate_current_bankroll(config):.2f}")
        logger.info("=" * 60)
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=args.debug)
        raise

if __name__ == "__main__":
    main()