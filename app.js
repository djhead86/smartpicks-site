// -------------------------------------------------------
// SmartPicksGPT - Clean Frontend Renderer
// -------------------------------------------------------

async function loadSmartPicks() {
    try {
        const res = await fetch("data/data.json?cache=" + Date.now());
        if (!res.ok) throw new Error("Failed to load data.json");

        const data = await res.json();
        renderAll(data);

    } catch (err) {
        console.error("loadSmartPicks error:", err);
    }
}

// -------------------------------
// Safe DOM setter
// -------------------------------
function setHTML(id, value) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = value;
}

// -------------------------------
// Render Everything
// -------------------------------
function renderAll(data) {
    renderTop10(data.top10 || []);
    renderDailySummary(data.daily_summary || {});
    renderPerformance(data.performance || {});
    renderHistory(data.history || []);
}

// -------------------------------
// TOP 10 PICKS TABLE
// -------------------------------
function renderTop10(picks) {
    const container = document.getElementById("top10");
    if (!container) return;

    if (!picks.length) {
        container.innerHTML = `<p>No picks available for the next 24 hours.</p>`;
        return;
    }

    let html = `
        <table class="table">
            <thead>
                <tr>
                    <th>Sport</th>
                    <th>Match</th>
                    <th>Team</th>
                    <th>Price</th>
                    <th>Prob</th>
                    <th>EV</th>
                    <th>Event Time</th>
                </tr>
            </thead>
            <tbody>
    `;

    picks.forEach(p => {
        html += `
            <tr>
                <td>${p.sport}</td>
                <td>${p.match}</td>
                <td>${p.team}</td>
                <td>${p.price}</td>
                <td>${(p.prob ?? 0).toFixed(3)}</td>
                <td>${(p.ev ?? 0).toFixed(4)}</td>
                <td>${p.event_time}</td>
            </tr>
        `;
    });

    html += `</tbody></table>`;
    container.innerHTML = html;
}

// -------------------------------
// DAILY SUMMARY
// -------------------------------
function renderDailySummary(sum) {
    setHTML("daily_date", sum.date || "—");
    setHTML("daily_num", sum.num_bets ?? 0);
    setHTML("daily_staked", (sum.staked ?? 0).toFixed(2));
    setHTML("daily_profit", (sum.profit ?? 0).toFixed(2));
    setHTML("daily_roi", (sum.roi_pct ?? 0).toFixed(2) + "%");
    setHTML("daily_bankroll", (sum.current_bankroll ?? 0).toFixed(2));
}

// -------------------------------
// OVERALL PERFORMANCE
// -------------------------------
function renderPerformance(p) {
    setHTML("perf_total", p.total_bets ?? 0);
    setHTML("perf_wins", p.wins ?? 0);
    setHTML("perf_losses", p.losses ?? 0);
    setHTML("perf_pushes", p.pushes ?? 0);
    setHTML("perf_bankroll", (p.current_bankroll ?? 0).toFixed(2));
    setHTML("perf_staked", (p.total_staked ?? 0).toFixed(2));
    setHTML("perf_profit", (p.total_profit ?? 0).toFixed(2));
    setHTML("perf_roi", (p.roi_pct ?? 0).toFixed(2) + "%");
}

// -------------------------------
// FULL BET HISTORY
// -------------------------------
function renderHistory(history) {
    const container = document.getElementById("history");
    if (!container) return;

    if (!history.length) {
        container.innerHTML = `<p>No history available yet.</p>`;
        return;
    }

    let html = `
        <table class="table">
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Sport</th>
                    <th>Match</th>
                    <th>Team</th>
                    <th>Result</th>
                    <th>Profit</th>
                    <th>Event Time</th>
                </tr>
            </thead>
            <tbody>
    `;

    history.forEach(h => {
        html += `
            <tr>
                <td>${h.date}</td>
                <td>${h.sport}</td>
                <td>${h.match}</td>
                <td>${h.team}</td>
                <td>${h.result}</td>
                <td>${h.actual_profit ?? "0.00"}</td>
                <td>${h.event_time}</td>
            </tr>
        `;
    });

    html += `</tbody></table>`;
    container.innerHTML = html;
}

// -------------------------------
// Auto-load on page open
// -------------------------------
loadSmartPicks();

// Refresh every 5 minutes
setInterval(loadSmartPicks, 5 * 60 * 1000);
