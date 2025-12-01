async function loadSmartPicks() {
    try {
        const res = await fetch("data/data.json?_=" + Date.now());
        const json = await res.json();
        renderDashboard(json);
    } catch (err) {
        console.error("Failed to load SmartPicks data:", err);
    }
}

// -------------------------------------------------------------
// MASTER RENDER
// -------------------------------------------------------------
function renderDashboard(json) {
    const summary = json.daily_summary || {};
    const perf = json.performance || {};
    const top10 = json.top10 || [];
    const history = json.history || [];

    renderDailySummary(summary);
    renderPerformance(perf);
    renderTop10(top10);
    renderHistory(history);
}

// -------------------------------------------------------------
// DAILY SUMMARY (today only)
// -------------------------------------------------------------
function renderDailySummary(summary) {
    const numBets = Number(summary.num_bets || 0);
    const staked = Number(summary.staked || 0);
    const profit = Number(summary.profit || 0);
    const roiPct = Number(summary.roi_pct || 0);
    const bankroll = Number(summary.current_bankroll || 0);

    safeSet("daily-bets", numBets.toFixed(0));
    safeSet("daily-staked", staked.toFixed(2));
    safeSet("daily-profit", profit.toFixed(2));
    safeSet("daily-roi", roiPct.toFixed(2) + "%");
    safeSet("daily-bankroll", "$" + bankroll.toFixed(2));
}

// -------------------------------------------------------------
// LIFETIME PERFORMANCE
// -------------------------------------------------------------
function renderPerformance(perf) {
    const totalBets = Number(perf.total_bets || 0);
    const wins = Number(perf.wins || 0);
    const losses = Number(perf.losses || 0);
    const pushes = Number(perf.pushes || 0);
    const bankroll = Number(perf.current_bankroll || 0);
    const totalStaked = Number(perf.total_staked || 0);
    const totalProfit = Number(perf.total_profit || 0);
    const roiPct = Number(perf.roi_pct || 0);

    safeSet("total-bets", totalBets.toFixed(0));
    safeSet("wins", wins.toFixed(0));
    safeSet("losses", losses.toFixed(0));
    safeSet("pushes", pushes.toFixed(0));
    safeSet("bankroll", "$" + bankroll.toFixed(2));
    safeSet("total-staked", "$" + totalStaked.toFixed(2));
    safeSet("total-profit", "$" + totalProfit.toFixed(2));
    safeSet("roi", roiPct.toFixed(2) + "%");
}

// -------------------------------------------------------------
// TOP 10 PICKS
// -------------------------------------------------------------
function renderTop10(top10) {
    const container = document.getElementById("top10");
    if (!container) return;

    container.innerHTML = "";

    top10.forEach(p => {
        const el = document.createElement("div");
        el.className = "pick-card";

        el.innerHTML = `
            <div class="match">${p.match}</div>
            <div class="team">${p.team}</div>
            <div class="details">
                <span>Market: ${p.market}</span>
                <span>Odds: +${p.price}</span>
                <span>EV: ${p.ev.toFixed(3)}</span>
                <span>Kelly: ${(p.kelly * 100).toFixed(2)}%</span>
                <span>Stake: ${p.recommended_stake.toFixed(2)}</span>
            </div>
            <div class="time">${p.event_time}</div>
        `;
        container.appendChild(el);
    });
}

// -------------------------------------------------------------
// FULL BET HISTORY
// -------------------------------------------------------------
function renderHistory(history) {
    const container = document.getElementById("history");
    if (!container) return;

    container.innerHTML = "";

    history.forEach(h => {
        const el = document.createElement("div");
        el.className = "history-row";

        el.innerHTML = `
            <div>${h.date}</div>
            <div>${h.match}</div>
            <div>${h.team}</div>
            <div>${h.market}</div>
            <div>+${h.price}</div>
            <div>${h.result}</div>
            <div>${h.actual_profit}</div>
            <div>${h.bankroll}</div>
        `;
        container.appendChild(el);
    });
}

// -------------------------------------------------------------
// SAFE DOM SETTER
// -------------------------------------------------------------
function safeSet(id, value) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = value;
}

// Start on load
loadSmartPicks();
