// SMARTPICKSGPT DASHBOARD SCRIPT
// ================================================
// Regenerated for Option A: Show only bets within
// the next 24 hours in the Bet History tab.
// ================================================

document.addEventListener("DOMContentLoaded", () => {
    loadData();
    setupTabs();
});

// ----------------------------
// Load data.json
// ----------------------------
async function loadData() {
    try {
        const response = await fetch("data/data.json?cache=" + Date.now());
        const data = await response.json();
        populateLastUpdated(data);
        populateTopPicks(data.top10);
        populateDailySummary(data.daily_summary);
        populatePerformance(data.performance);
        populateBetHistoryFiltered(data.history);
        renderCharts(data.analytics);
    } catch (err) {
        console.error("Failed to load data.json:", err);
    }
}

// ----------------------------
// Last Updated timestamp
// ----------------------------
function populateLastUpdated(data) {
    const el = document.getElementById("last-updated");
    if (!el) return;
    el.textContent = "Last update: " + new Date(data.last_updated).toLocaleString();
}

// ----------------------------
// TOP PICKS
// ----------------------------
function populateTopPicks(topPicks) {
    const container = document.getElementById("top-picks");
    if (!container) return;

    container.innerHTML = "";

    topPicks.forEach(pick => {
        const card = document.createElement("div");
        card.className = "pick-card";

        card.innerHTML = `
            <h3>${formatSport(pick.sport)}</h3>
            <p><strong>${pick.match}</strong></p>
            <p>Pick: <strong>${pick.team}</strong> (${pick.market.toUpperCase()})</p>
            <p>Price: ${pick.price}</p>
            <p>Probability: ${(pick.prob * 100).toFixed(1)}%</p>
            <p>Confidence: ${(pick.confidence * 100).toFixed(1)}%</p>
            <p>Stake: ${pick.recommended_stake.toFixed(2)} units</p>
            <p class="why">${pick.why}</p>
            <p class="event-time">Event: ${formatDateTime(pick.event_time)}</p>
        `;

        container.appendChild(card);
    });
}

// ----------------------------
// DAILY SUMMARY
// ----------------------------
function populateDailySummary(sum) {
    const el = document.getElementById("summary");
    if (!el) return;

    el.innerHTML = `
        <div class="summary-grid">
            <div class="summary-item"><strong>Bets Today:</strong> ${sum.total_bets}</div>
            <div class="summary-item"><strong>Record:</strong> ${sum.record}</div>
            <div class="summary-item"><strong>Win %:</strong> ${(sum.win_pct * 100).toFixed(1)}%</div>
            <div class="summary-item"><strong>Units Wagered:</strong> ${sum.units_wagered.toFixed(2)}</div>
            <div class="summary-item"><strong>Expected Profit:</strong> ${sum.expected_profit.toFixed(2)}</div>
            <div class="summary-item"><strong>Actual Profit:</strong> ${sum.actual_profit.toFixed(2)}</div>
            <div class="summary-item"><strong>ROI:</strong> ${(sum.roi_pct * 100).toFixed(2)}%</div>
            <div class="summary-item"><strong>Bankroll:</strong> ${sum.bankroll.toFixed(2)}</div>
        </div>
    `;
}

// ----------------------------
// PERFORMANCE OVERALL
// ----------------------------
function populatePerformance(perf) {
    const el = document.getElementById("performance");
    if (!el) return;

    el.innerHTML = `
        <div class="perf-grid">
            <div>Total Bets: ${perf.total_bets}</div>
            <div>Wins: ${perf.wins}</div>
            <div>Losses: ${perf.losses}</div>
            <div>Win %: ${(perf.win_pct * 100).toFixed(1)}%</div>
            <div>Units Wagered: ${perf.units_wagered.toFixed(2)}</div>
            <div>Expected Profit: ${perf.expected_profit.toFixed(2)}</div>
            <div>Actual Profit: ${perf.actual_profit.toFixed(2)}</div>
            <div>ROI: ${(perf.roi_pct * 100).toFixed(2)}%</div>
            <div>Current Bankroll: ${perf.current_bankroll.toFixed(2)}</div>
        </div>
    `;
}

// ------------------------------------------------------
// OPTION A: BET HISTORY — ONLY NEXT 24 HOURS
// ------------------------------------------------------
function populateBetHistoryFiltered(history) {
    const table = document.getElementById("history-table-body");
    if (!table) return;

    table.innerHTML = "";

    const now = new Date();
    const cutoff = new Date(now.getTime() + 24 * 60 * 60 * 1000);

    const filtered = history.filter(item => {
        const eventTime = new Date(item.event_time);
        return eventTime >= now && eventTime <= cutoff;
    });

    filtered.forEach(row => {
        const tr = document.createElement("tr");

        tr.innerHTML = `
            <td>${row.date}</td>
            <td>${formatDateTime(row.event_time)}</td>
            <td>${formatSport(row.sport)}</td>
            <td>${row.match}</td>
            <td>${row.team} (${row.market})</td>
            <td>${row.price}</td>
            <td>${row.stake.toFixed(2)}</td>
            <td>${row.result}</td>
            <td>${row.profit.toFixed(2)}</td>
            <td>${row.bankroll_after.toFixed(2)}</td>
        `;

        table.appendChild(tr);
    });
}

// ----------------------------
// CHARTS
// ----------------------------
function renderCharts(analytics) {
    if (!analytics) return;

    renderROIChart(analytics.roi_history);
    renderBankrollChart(analytics.bankroll_history);
    renderWinrateChart(analytics.sport_winrates);
}

// ROI Chart
function renderROIChart(history) {
    const ctx = document.getElementById("roi-chart");
    if (!ctx) return;

    new Chart(ctx, {
        type: "line",
        data: {
            labels: history.map(e => e.date),
            datasets: [{
                label: "ROI %",
                data: history.map(e => e.roi_pct * 100),
                borderWidth: 2,
            }]
        }
    });
}

// Bankroll Chart
function renderBankrollChart(history) {
    const ctx = document.getElementById("bankroll-chart");
    if (!ctx) return;

    new Chart(ctx, {
        type: "line",
        data: {
            labels: history.map(e => e.date),
            datasets: [{
                label: "Bankroll",
                data: history.map(e => e.bankroll),
                borderWidth: 2,
            }]
        }
    });
}

// Sport Winrate Chart
function renderWinrateChart(winrates) {
    const ctx = document.getElementById("winrate-chart");
    if (!ctx) return;

    const labels = Object.keys(winrates);
    const values = Object.values(winrates).map(v => v * 100);

    new Chart(ctx, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                label: "Win % by Sport",
                data: values,
                borderWidth: 1
            }]
        }
    });
}

// ----------------------------
// TAB HANDLER
// ----------------------------
function setupTabs() {
    const buttons = document.querySelectorAll(".tab-button");
    const contents = document.querySelectorAll(".tab-content");

    buttons.forEach(btn => {
        btn.addEventListener("click", () => {
            buttons.forEach(b => b.classList.remove("active"));
            contents.forEach(c => c.classList.remove("active"));

            btn.classList.add("active");
            document.getElementById(btn.dataset.tab).classList.add("active");
        });
    });
}

// ----------------------------
// HELPERS
// ----------------------------
function formatDateTime(dtString) {
    return new Date(dtString).toLocaleString();
}

function formatSport(s) {
    return s.replace(/_/g, " ").toUpperCase();
}

