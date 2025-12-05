// ===============================
// SmartPicks Frontend v2
// Fully Updated & Crash-Proof
// ===============================

// Map backend sport keys → DOM IDs in index.html
const SPORT_KEY_TO_DOM_ID = {
    "basketball_nba": "nba-picks",
    "americanfootball_nfl": "nfl-picks",
    "icehockey_nhl": "nhl-picks",
    "soccer_epl": "epl-picks",
    "soccer_uefa_champs_league": "uefa-picks",
    "mma_mixed_martial_arts": "ufc-picks"
};

// Debugging toggle
const DEBUG = false;
function log(...args) {
    if (DEBUG) console.log("[SmartPicks]", ...args);
}

// ===============================
// Utility: Format Money
// ===============================
function fmtMoney(v) {
    return "$" + Number(v).toFixed(2);
}

// ===============================
// Fetch JSON Safely
// ===============================
async function loadJSON(url) {
    try {
        const res = await fetch(url + "?t=" + Date.now());
        if (!res.ok) throw new Error("HTTP " + res.status);
        return await res.json();
    } catch (err) {
        showError(`Failed to load ${url}: ${err}`);
        return null;
    }
}

// ===============================
// Error Handler
// ===============================
function showError(msg) {
    const box = document.getElementById("error-message");
    const text = document.getElementById("error-text");
    box.style.display = "block";
    text.textContent = msg;
    console.error("SmartPicks Error:", msg);
}

// ===============================
// Create a Pick Card
// ===============================
function createPickCard(p) {
    return `
        <div class="pick-card">
            <h4>${p.event}</h4>
            <p><strong>Pick:</strong> ${p.team}</p>
            <p><strong>Market:</strong> ${p.market}</p>
            <p><strong>Odds:</strong> ${p.odds}</p>
            <p><strong>EV:</strong> ${Number(p.ev).toFixed(3)}</p>
            <p><strong>Smart Score:</strong> ${Number(p.smart_score).toFixed(3)}</p>
            <p><strong>Stake:</strong> ${fmtMoney(p.stake)}</p>
            <p><strong>Status:</strong> ${p.status}</p>
        </div>
    `;
}

// ===============================
// Render Picks by Sport
// ===============================
function renderPicks(data) {
    const pickCards = data.pick_cards || {};

    for (const sportKey in pickCards) {
        const domId = SPORT_KEY_TO_DOM_ID[sportKey];

        if (!domId) {
            log("No DOM mapping for sport:", sportKey);
            continue;
        }

        const container = document.getElementById(domId);
        if (!container) {
            console.error("Missing DOM element for:", domId);
            continue;
        }

        const picks = pickCards[sportKey];

        if (!picks || picks.length === 0) {
            container.innerHTML = `<div class="loading">No picks available.</div>`;
            continue;
        }

        container.innerHTML = picks.map(createPickCard).join("");
    }
}

// ===============================
// Render Parlay
// ===============================
function renderParlay(data) {
    const card = document.getElementById("parlay-card");
    const parlay = data.parlay || [];

    if (!card) return;

    if (!parlay.length) {
        card.innerHTML = `<div class="loading">No parlay available.</div>`;
        return;
    }

    card.innerHTML = parlay.map(createPickCard).join("");
}

// ===============================
// Render Bankroll + Stats
// ===============================
function renderStats(data) {
    document.getElementById("bankroll").textContent = fmtMoney(data.bankroll || 0);
    document.getElementById("open-bets").textContent = data.open_bets || 0;
    document.getElementById("win-rate").textContent = (data.win_rate || 0) + "%";
    document.getElementById("roi").textContent = (data.roi || 0) + "%";
    document.getElementById("last-updated").textContent = data.timestamp || "--";
}

// ===============================
// Render Live Score Ticker
// ===============================
function renderScores(scores) {
    const ticker = document.getElementById("ticker");

    if (!scores || !scores.scores || scores.scores.length === 0) {
        ticker.innerHTML = `<div class="ticker-item">No live scores available</div>`;
        return;
    }

    ticker.innerHTML = scores.scores
        .map(s => `<div class="ticker-item">${s.league}: ${s.event} — ${s.score} (${s.status})</div>`)
        .join("");
}

// ===============================
// Main Loader
// ===============================
async function loadAll() {
    log("Loading SmartPicks data…");

    const data = await loadJSON("data.json");
    const scores = await loadJSON("scores.json");

    if (!data) return;

    renderStats(data);
    renderParlay(data);
    renderPicks(data);

    if (scores) renderScores(scores);
}

// Run on startup
loadAll();

// Refresh every 60 seconds
setInterval(loadAll, 60000);
