console.log("SmartPicksGPT frontend initialized.");

const DATA_URL = "data/data.json";

// DOM references
const picksBox = document.getElementById("picks-container");
const summaryBox = document.getElementById("daily-summary-box");
const perfBox = document.getElementById("performance-box");
const historyBody = document.getElementById("history-body");
const lastUpdatedSpan = document.getElementById("last-updated");

// MAIN LOADER
async function loadSmartPicks() {
  try {
    const response = await fetch(DATA_URL + "?_=" + Date.now()); // cache-bust
    if (!response.ok) throw new Error("Failed to load data.json");

    const data = await response.json();
    console.log("Loaded SmartPicks data:", data);

    if (data.last_updated && lastUpdatedSpan) {
      lastUpdatedSpan.textContent = "Last updated: " + data.last_updated;
    }

    renderDailySummary(data.daily_summary);
    renderPicks(data.top10);
    renderPerformance(data.performance);
    renderHistory(data.history);
  } catch (err) {
    console.error(err);
    picksBox.innerHTML = `<div class="error">❌ Failed to load SmartPicks data.</div>`;
  }
}

// ----------------------------
// RENDER DAILY SUMMARY
// ----------------------------
function renderDailySummary(ds) {
  if (!ds) {
    summaryBox.innerHTML = "<p>No summary available.</p>";
    return;
  }

  const winPct = (ds.win_pct || 0) * 100;
  const roiPct = (ds.roi_pct || 0) * 100;

  summaryBox.innerHTML = `
    <p><strong>Date:</strong> ${ds.date}</p>
    <p><strong>Total Bets:</strong> ${ds.total_bets}</p>
    <p><strong>Record:</strong> ${ds.record}</p>
    <p><strong>Win %:</strong> ${winPct.toFixed(1)}%</p>
    <p><strong>Units Wagered:</strong> ${Number(ds.units_wagered || 0).toFixed(2)}</p>
    <p><strong>Expected Profit:</strong> ${Number(ds.expected_profit || 0).toFixed(2)}</p>
    <p><strong>Actual Profit:</strong> ${Number(ds.actual_profit || 0).toFixed(2)}</p>
    <p><strong>ROI:</strong> ${roiPct.toFixed(1)}%</p>
    <p><strong>Bankroll:</strong> ${Number(ds.bankroll || 0).toFixed(2)}</p>
  `;
}

// ----------------------------
// RENDER TOP 10 PICKS
// ----------------------------
function renderPicks(picks) {
  if (!picks || picks.length === 0) {
    picksBox.innerHTML = "<p>No picks available.</p>";
    return;
  }

  let html = "";

  picks.forEach((p) => {
    const prob = p.prob ? (p.prob * 100).toFixed(1) : "--";
    const ev = typeof p.ev === "number" ? (p.ev * 100).toFixed(2) : "0.00";
    const kelly = typeof p.kelly === "number" ? (p.kelly * 100).toFixed(2) : "0.00";

    html += `
      <div class="pick-card">
        <h3>${p.match}</h3>
        <p><strong>Sport:</strong> ${p.sport}</p>
        <p><strong>Team:</strong> ${p.team}</p>
        <p><strong>Market:</strong> ${p.market}</p>
        <p><strong>Price:</strong> ${p.price}</p>
        <p><strong>Probability:</strong> ${prob}%</p>
        <p><strong>EV:</strong> ${ev}%</p>
        <p><strong>Kelly %:</strong> ${kelly}%</p>
        <p><em>${p.why || ""}</em></p>
      </div>
    `;
  });

  picksBox.innerHTML = html;
}

// ----------------------------
// RENDER PERFORMANCE
// ----------------------------
function renderPerformance(p) {
  if (!p) {
    perfBox.innerHTML = "<p>No performance data.</p>";
    return;
  }

  const winPct = (p.win_pct || 0) * 100;
  const roiPct = (p.roi_pct || 0) * 100;

  perfBox.innerHTML = `
    <p><strong>Total Bets:</strong> ${p.total_bets}</p>
    <p><strong>Wins:</strong> ${p.wins}</p>
    <p><strong>Losses:</strong> ${p.losses}</p>
    <p><strong>Pushes:</strong> ${p.pushes}</p>
    <p><strong>Units Wagered:</strong> ${Number(p.units_wagered || 0).toFixed(2)}</p>
    <p><strong>Expected Profit:</strong> ${Number(p.expected_profit || 0).toFixed(2)}</p>
    <p><strong>Actual Profit:</strong> ${Number(p.actual_profit || 0).toFixed(2)}</p>
    <p><strong>Win %:</strong> ${winPct.toFixed(1)}%</p>
    <p><strong>ROI:</strong> ${roiPct.toFixed(1)}%</p>
    <p><strong>Current Bankroll:</strong> ${Number(p.current_bankroll || 0).toFixed(2)}</p>
  `;
}

// ----------------------------
// RENDER HISTORY
// ----------------------------
function renderHistory(history) {
  if (!historyBody) return;

  if (!history || history.length === 0) {
    historyBody.innerHTML = `
      <tr>
        <td colspan="10" style="text-align:center;">No history available.</td>
      </tr>
    `;
    return;
  }

  let rows = "";

  history.forEach((h) => {
    const date = h.date || "";
    const eventTime = h.event_time || "";
    const sport = h.sport || "";
    const match = h.match || "";
    const bet = `${h.team || ""} (${h.market || ""})`;
    const price = h.price ?? "";
    const stake = Number(h.stake || 0).toFixed(2);
    const result = h.result || "";
    const profit = Number(h.profit ?? h.actual_profit ?? 0).toFixed(2);
    const bankrollAfter = Number(h.bankroll_after || 0).toFixed(2);

    rows += `
      <tr>
        <td>${date}</td>
        <td>${eventTime}</td>
        <td>${sport}</td>
        <td>${match}</td>
        <td>${bet}</td>
        <td>${price}</td>
        <td>${stake}</td>
        <td>${result}</td>
        <td>${profit}</td>
        <td>${bankrollAfter}</td>
      </tr>
    `;
  });

  historyBody.innerHTML = rows;
}

loadSmartPicks();

