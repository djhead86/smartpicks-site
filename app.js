// ===============================
// SmartPicks Frontend v2.1
// FIXED - Data Structure Mapping
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
const DEBUG = true;  // Set to true to see console logs
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
        const data = await res.json();
        log(`Loaded ${url}:`, data);
        return data;
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
    if (box && text) {
        box.style.display = "block";
        text.textContent = msg;
    }
    console.error("SmartPicks Error:", msg);
}

// ===============================
// Create a Pick Card
// ===============================
function createPickCard(p) {
    // Safe fallbacks for missing fields
    const event = p.matchup || p.event || "Unknown Event";
    const pick = p.pick || p.team || p.side || "N/A";
    const market = p.pick_type || p.market || p.bet_type || "N/A";
    const odds = p.odds || p.price || "N/A";
    const line = p.line ? ` (${p.line})` : "";
    const ev = p.ev !== undefined ? Number(p.ev).toFixed(2) : "N/A";
    const score = p.smart_score !== undefined ? Number(p.smart_score).toFixed(2) : "N/A";
    const stake = p.stake !== undefined ? `$${p.stake.toFixed(2)}` : "$0.00";
    const status = p.status || "pending";
    const sport = p.sport || "";

    return `
        <div class="pick-card">
            <div class="pick-header">
                <span class="pick-sport">${sport}</span>
                <span class="pick-status status-${status}">${status}</span>
            </div>
            <h4 class="pick-event">${event}</h4>
            <div class="pick-details">
                <div class="pick-row">
                    <span class="pick-label">Pick:</span>
                    <span class="pick-value"><strong>${pick}${line}</strong></span>
                </div>
                <div class="pick-row">
                    <span class="pick-label">Market:</span>
                    <span class="pick-value">${market}</span>
                </div>
                <div class="pick-row">
                    <span class="pick-label">Odds:</span>
                    <span class="pick-value">${odds > 0 ? '+' : ''}${odds}</span>
                </div>
                <div class="pick-metrics">
                    <div class="metric">
                        <span class="metric-label">EV</span>
                        <span class="metric-value">${ev}%</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Score</span>
                        <span class="metric-value">${score}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Stake</span>
                        <span class="metric-value">${stake}</span>
                    </div>
                </div>
            </div>
        </div>
    `;
}


// ===============================
// Render Picks by Sport
// ===============================
function renderPicks(data) {
    const pickCards = data.pick_cards || {};
    log("Rendering picks:", pickCards);

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
            log(`No picks for ${sportKey}`);
            continue;
        }

        log(`Rendering ${picks.length} picks for ${sportKey}`);
        container.innerHTML = picks.map(createPickCard).join("");
    }
}

// ===============================
// Render Parlay
// ===============================
function renderParlay(data) {
    const card = document.getElementById("parlay-card");
    
    // FIXED: Look for parlay_card instead of parlay
    const parlayData = data.parlay_card;
    
    if (!card) {
        log("Parlay card element not found");
        return;
    }

    if (!parlayData || !parlayData.picks || parlayData.picks.length === 0) {
        card.innerHTML = `<div class="loading">No parlay available.</div>`;
        log("No parlay data available");
        return;
    }

    log("Rendering parlay:", parlayData);
    
    // Create parlay header
    const parlayHeader = `
        <div class="parlay-header">
            <h3>${parlayData.legs}-Leg Parlay</h3>
            <div class="parlay-stats">
                <span>Total Stake: ${fmtMoney(parlayData.total_stake)}</span>
                <span>Total EV: ${parlayData.total_ev.toFixed(2)}%</span>
            </div>
        </div>
    `;
    
    const parlayPicks = parlayData.picks.map(createPickCard).join("");
    
    card.innerHTML = parlayHeader + '<div class="parlay-picks">' + parlayPicks + '</div>';
}

// ===============================
// Render Bankroll + Stats
// ===============================
function renderStats(data) {
    log("Rendering stats:", data);
    
    // FIXED: Extract from performance object
    const performance = data.performance?.overall || {};
    const winRate = performance.win_rate || 0;
    const roi = performance.roi || 0;
    
    document.getElementById("bankroll").textContent = fmtMoney(data.bankroll || 0);
    document.getElementById("open-bets").textContent = data.open_bets || 0;
    document.getElementById("win-rate").textContent = winRate.toFixed(1) + "%";
    document.getElementById("roi").textContent = roi.toFixed(1) + "%";
    
    // FIXED: Use generated_at instead of timestamp
    const timestamp = data.generated_at || data.timestamp || "--";
    const displayTime = timestamp !== "--" ? new Date(timestamp).toLocaleString() : "--";
    document.getElementById("last-updated").textContent = displayTime;
    
    log("Stats rendered successfully");
}

// ===============================
// Render Live Score Ticker
// ===============================
function renderScores(scores) {
    const ticker = document.getElementById("ticker");

    if (!ticker) {
        log("Ticker element not found");
        return;
    }

    if (!scores || !scores.scores || scores.scores.length === 0) {
        ticker.innerHTML = '<div class="ticker-item">No live scores available</div>';
        log("No scores available");
        return;
    }

    log(`Rendering ${scores.scores.length} scores`);
    
    // FIXED: Return the mapped HTML string
    ticker.innerHTML = scores.scores
        .map(s => {
            const league = s.league || "";
            const prefix = league ? league + ": " : "";
            const score = s.score || "";
            const status = s.status || "";
            const scoreDisplay = score ? ` — ${score}` : "";
            const statusDisplay = status ? ` (${status})` : "";
            return `<div class="ticker-item">${prefix}${s.event}${scoreDisplay}${statusDisplay}</div>`;
        })
        .join("");
}

// ===============================
// Main Loader
// ===============================
async function loadAll() {
    log("=== Loading SmartPicks data ===");

    const data = await loadJSON("data.json");
    const scores = await loadJSON("scores.json");

    if (!data) {
        showError("Failed to load main data");
        return;
    }

    log("Data loaded successfully, rendering...");
    
    renderStats(data);
    renderParlay(data);
    renderPicks(data);

    if (scores) {
        renderScores(scores);
    } else {
        log("No scores data available");
    }
    
    log("=== Rendering complete ===");
}

// Run on startup
log("SmartPicks initializing...");
loadAll();

// Refresh every 60 seconds
setInterval(loadAll, 60000);
log("Auto-refresh enabled (60s interval)");