from flask import Flask, request, jsonify
from pathlib import Path
import subprocess

from smart_picks import (
    Config,
    DEFAULT_CONFIG_PATH,
    load_bet_history,
    save_bet_history,
    apply_grade_to_bet,
)

app = Flask(__name__)

@app.post("/grade")
def grade():
    data = request.get_json(force=True) or {}
    bet_id = data.get("bet_id")
    outcome = data.get("outcome")
    if not bet_id or not outcome:
        return jsonify({"status": "error", "message": "bet_id and outcome required"}), 400

    config = Config.load(DEFAULT_CONFIG_PATH)
    history_rows = load_bet_history(config.bet_history_path)

    if not apply_grade_to_bet(history_rows, bet_id, outcome, config.starting_bankroll):
        return jsonify({"status": "error", "message": "could not grade bet"}), 400

    save_bet_history(history_rows, config.bet_history_path)

    # Rebuild data.json so UI sees changes
    subprocess.run(
        ["python3", "smart_picks.py"],
        cwd=Path(__file__).parent,
        check=False,
    )

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    # run with: python3 grader_api.py
    app.run(host="127.0.0.1", port=5001, debug=True)

