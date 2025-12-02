import json
from datetime import datetime

def is_valid_pick(p):
    """Return True if the pick is real (not seed data)."""
    # Stake must be positive
    if p.get("stake", 0) == 0:
        return False

    # Must have probability & edge info
    if p.get("prob", 0) <= 0 or p.get("adj_ev", 0) <= 0:
        return False

    # Must have a future event time (not past example data)
    try:
        event_dt = datetime.strptime(p.get("event_time", ""), "%Y-%m-%d %H:%M:%00")
        if event_dt < datetime.now():
            return False
    except Exception:
        return False

    return True

def clean_data_json(filepath="data.json"):
    with open(filepath, "r") as f:
        data = json.load(f)

    # -----------------------------
    # Clean Top Picks
    # -----------------------------
    original_top = len(data.get("top10", []))
    data["top10"] = [p for p in data.get("top10", []) if is_valid_pick(p)]
    cleaned_top = len(data["top10"])

    # -----------------------------
    # Clean History
    # -----------------------------
    original_hist = len(data.get("history", []))
    data["history"] = [h for h in data.get("history", []) if is_valid_pick(h)]
    cleaned_hist = len(data["history"])

    # -----------------------------
    # Recalculate Sport Winrates
    # -----------------------------
    def build_sport_stats(history):
        stats = {}
        for h in history:
            s = h["sport"]
            if s not in stats:
                stats[s] = { "bets": 0, "wins": 0, "losses": 0, "pushes": 0 }

            stats[s]["bets"] += 1

            if h["result"] == "WIN":
                stats[s]["wins"] += 1
            elif h["result"] == "LOSS":
                stats[s]["losses"] += 1
            elif h["result"] == "PUSH":
                stats[s]["pushes"] += 1

        # Compute win pct
        for s,v in stats.items():
            if v["bets"] > 0:
                v["win_pct"] = v["wins"] / v["bets"]
            else:
                v["win_pct"] = 0.0

        return stats

    cleaned_stats = build_sport_stats(data["history"])
    data["analytics"]["sport_kpis"] = cleaned_stats
    data["analytics"]["sport_winrates"] = { k: v["win_pct"] for k,v in cleaned_stats.items() }

    # -----------------------------
    # Recalculate Stake Distribution
    # -----------------------------
    stake_by_sport = {}
    for h in data["history"]:
        stake_by_sport[h["sport"]] = stake_by_sport.get(h["sport"], 0) + h["stake"]

    total_stake = sum(stake_by_sport.values()) or 1

    data["analytics"]["stake_distribution"] = {
        "by_sport_units": stake_by_sport,
        "by_sport_pct": { k: v/total_stake for k,v in stake_by_sport.items() }
    }

    # -----------------------------
    # SAVE CLEANED DATA
    # -----------------------------
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    print(f"--- CLEANING COMPLETE ---")
    print(f"Top picks: {original_top} → {cleaned_top}")
    print(f"History:   {original_hist} → {cleaned_hist}")
    print(f"--------------------------------")

if __name__ == "__main__":
    clean_data_json("data.json")

