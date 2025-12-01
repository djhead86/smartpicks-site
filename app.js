console.log("SmartPicksGPT frontend initialized.");

const DATA_URL = "data/data.json";
const AUTO_REFRESH_MS = 2 * 60 * 60 * 1000; // 2 hours

// DOM
const picksGrid        = document.getElementById("picks-grid");
const todayBets        = document.getElementById("today-bets");
const todayRecord      = document.getElementById("today-record");
const todayUnits       = document.getElementById("today-units");
const todayProfit      = document.getElementById("today-profit");
const overallBankroll  = document.getElementById("overall-bankroll");
const overallPL        = document.getElementById("overall-pl");
const overallLastDay   = document.getElementById("overall-lastday");
const bankrollSummary  = document.getElementById("bankroll-summary");
const lastUpdated      = document.getElementById("last-updated");

let bankrollChartInstance   = null;
let roiChartInstance        = null;
let sportWinChartInstance   = null;
let confidenceChartInstance = null;

async function loadSmartPicks() {
    try {
        const res = await fetch(DATA_URL + "?cachebust=" + Date.now());
        if (!res.ok) throw new Error("Failed to load data.json: " + res.status);
        const data = await res.json();
        console.log("Loaded SmartPicks data:", data);

        const daily = data.daily_summary;
        const perf  = data.performance;
        const picks = data.top10;

        renderTodayStats(daily);
        renderOverallStats(perf);
        renderBankrollSummary(perf);
        renderPicks(picks);
        renderBankrollChart(perf);
        renderRoiChart(perf);
        renderSportWinChart(perf);
        renderConfidenceChart(picks);

        lastUpdated.innerText = "Last update: " + new Date().toLocaleString();

    } catch (e) {
        console.error(e);
        if (picksGrid) {
            picksGrid.innerHTML = "<p>❌ Failed to load SmartPicks data.</p>";
        }
    }
}

// ---------------- TODAY / OVERALL ----------------

function renderTodayStats(s) {
    if (!s) return;
    todayBets.textContent   = s.total_bets;
    todayRecord.textContent = `${s.record} (${s.win_pct.toFixed(1)}%)`;
    todayUnits.textContent  = s.units_wagered.toFixed(2) + "u";
    todayProfit.textContent = s.actual_profit.toFixed(2) + "u";
}

function renderOverallStats(p) {
    if (!p) return;
    overallBankroll.textContent = p.current_bankroll.toFixed(2) + "u";
    overallPL.textContent       = p.actual_profit.toFixed(2) + "u";

    // last day change = last ROI entry if available
    if (p.roi_history && p.roi_history.length) {
        const last = p.roi_history[p.roi_history.length - 1];
        overallLastDay.textContent = last.toFixed(2) + "%";
    } else {
        overallLastDay.textContent = "--";
    }
}

function renderBankrollSummary(p) {
    bankrollSummary.innerHTML = `
        <p><strong>Total Bets:</strong> ${p.total_bets}</p>
        <p><strong>P/L:</strong> ${p.actual_profit.toFixed(2)}u</p>
        <p><strong>ROI:</strong> ${p.roi_pct.toFixed(2)}%</p>
        <p><strong>Bankroll:</strong> ${p.current_bankroll.toFixed(2)}u</p>
    `;
}

// ---------------- PICKS GRID ----------------

function renderPicks(picks) {
    picksGrid.innerHTML = "";
    if (!picks || !picks.length) {
        picksGrid.innerHTML = "<p>No picks today.</p>";
        return;
    }

    picks.forEach((p, idx) => {
        const card = document.createElement("div");
        card.className = "pick-card";

        card.innerHTML = `
            <div class="pick-rank">#${idx + 1}</div>
            <div class="pick-match">${p.match}</div>
            <div class="pick-team">${p.team}</div>
            <div class="pick-market">Market: ${p.market}</div>
            <div class="pick-price">Price: ${p.price}</div>
            <div class="pick-prob">Prob: ${(p.prob * 100).toFixed(1)}%</div>
            <div class="pick-ev">Adj EV: ${p.adj_ev.toFixed(3)}</div>
            <div class="pick-kelly">Kelly: ${p.kelly.toFixed(3)}</div>
            <div class="pick-why">${p.why}</div>
        `;
        picksGrid.appendChild(card);
    });
}

// ---------------- CHARTS ----------------

function renderBankrollChart(perf) {
    const ctx = document.getElementById("bankrollChart").getContext("2d");
    if (bankrollChartInstance) bankrollChartInstance.destroy();

    const labels = perf.bankroll_history.map((_, i) => i + 1);
    bankrollChartInstance = new Chart(ctx, {
        type: "line",
        data: {
            labels,
            datasets: [{
                label: "Bankroll (units)",
                data: perf.bankroll_history,
                borderWidth: 2,
                tension: 0.2
            }]
        },
        options: { responsive: true }
    });
}

function renderRoiChart(perf) {
    const ctx = document.getElementById("roiChart").getContext("2d");
    if (roiChartInstance) roiChartInstance.destroy();

    const labels = perf.roi_history.map((_, i) => i + 1);
    roiChartInstance = new Chart(ctx, {
        type: "line",
        data: {
            labels,
            datasets: [{
                label: "ROI (%)",
                data: perf.roi_history,
                borderWidth: 2,
                tension: 0.2
            }]
        },
        options: { responsive: true }
    });
}

function renderSportWinChart(perf) {
    const ctx = document.getElementById("sportWinChart").getContext("2d");
    if (sportWinChartInstance) sportWinChartInstance.destroy();

    const statsObj = perf.win_pct_by_sport || {};
    const labels = Object.keys(statsObj);
    const values = labels.map(k => statsObj[k].win_pct);

    sportWinChartInstance = new Chart(ctx, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                label: "Win % by Sport",
                data: values,
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            scales: { y: { beginAtZero: true, max: 100 } }
        }
    });
}

function renderConfidenceChart(picks) {
    const ctx = document.getElementById("confidenceChart").getContext("2d");
    if (confidenceChartInstance) confidenceChartInstance.destroy();

    if (!picks || !picks.length) return;

    const labels = picks.map((_, i) => "#" + (i + 1));
    const probs  = picks.map(p => p.prob * 100);

    confidenceChartInstance = new Chart(ctx, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                label: "Model Probability (%)",
                data: probs,
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            scales: { y: { beginAtZero: true, max: 100 } }
        }
    });
}

// Start + auto-refresh
document.addEventListener("DOMContentLoaded", () => {
    loadSmartPicks();
    setInterval(loadSmartPicks, AUTO_REFRESH_MS);
});
