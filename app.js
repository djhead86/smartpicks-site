// Load the JSON once and fan it out to all tabs
fetch('data/data.json')
  .then(r => r.json())
  .then(json => {
    const top10       = json.top10 || [];
    const history     = json.history || [];
    const summary     = json.daily_summary || null;
    const performance = json.performance || null;

    // Update header timestamp
    const headerMeta = document.getElementById("last-updated");
    if (headerMeta) {
      const srcDate = summary?.date || new Date().toISOString().slice(0, 10);
      headerMeta.textContent = `Updated: ${srcDate}`;
    }

    renderTopPicks(top10);
    renderHistory(history);
    renderSummary(summary, performance);
    buildGraphics(performance, history);

  })
  .catch(err => {
    console.error("Failed to load data.json:", err);
  });

/* ---------- TOP PICKS TAB ---------- */

function renderTopPicks(picks) {
  const container = document.getElementById('picks');
  if (!container) return;

  container.innerHTML = "";

  if (!picks.length) {
    container.innerHTML = `<p>No picks available.</p>`;
    return;
  }

  picks.forEach((pick, index) => {
    const evPercent = safePercent(pick.ev);

    const el = document.createElement('div');
    el.className = 'pick';

    el.innerHTML = `
      <h3>#${index + 1} — ${pick.team} (${(pick.market || '').toUpperCase()})</h3>

      <p><strong>Match:</strong> ${pick.match}</p>
      <p><strong>Line:</strong> ${pick.price}</p>
      <p><strong>EV:</strong> ${pick.ev}</p>

      <div class="ev-bar">
        <div class="ev-bar-fill" style="width: ${evPercent}%;"></div>
      </div>

      <p class="explanation">
        ${pick.explanation || "No explanation available."}
      </p>
    `;

    container.appendChild(el);
  });
}

/* ---------- HISTORY TAB ---------- */

function renderHistory(history) {
  const container = document.getElementById('history');
  if (!container) return;

  container.innerHTML = "";

  if (!history.length) {
    container.innerHTML = `<p>No bet history available yet.</p>`;
    return;
  }

  const table = document.createElement('table');
  table.className = 'history-table';

  const thead = document.createElement('thead');
  thead.innerHTML = `
    <tr>
      <th>Date</th>
      <th>Sport</th>
      <th>Match</th>
      <th>Bet</th>
      <th>Market</th>
      <th>Price</th>
      <th>Stake</th>
      <th>Result</th>
      <th>P/L</th>
      <th>Bankroll</th>
    </tr>
  `;
  table.appendChild(thead);

  const tbody = document.createElement('tbody');

  history.forEach(entry => {
    const tr = document.createElement('tr');

    const result = (entry.result || '').toUpperCase();
    let resultClass = 'result-pending';
    if (result === 'WIN') resultClass = 'result-win';
    else if (result === 'LOSS') resultClass = 'result-loss';

    tr.innerHTML = `
      <td>${entry.date || ''}</td>
      <td>${entry.sport || ''}</td>
      <td>${entry.match || ''}</td>
      <td>${entry.team || ''}</td>
      <td>${entry.market || ''}</td>
      <td>${entry.price || ''}</td>
      <td>${entry.stake || ''}</td>
      <td class="${resultClass}">${result || ''}</td>
      <td>${entry.actual_profit || ''}</td>
      <td>${entry.bankroll || ''}</td>
    `;

    tbody.appendChild(tr);
  });

  table.appendChild(tbody);
  container.appendChild(table);
}

/* ---------- SUMMARY TAB ---------- */

function renderSummary(summary, performance) {
  const container = document.getElementById('summary');
  if (!container) return;

  container.innerHTML = "";

  if (!summary && !performance) {
    container.innerHTML = `<p>No summary data available.</p>`;
    return;
  }

  const wrapper = document.createElement('div');

  // Daily summary block
  if (summary) {
    const daily = document.createElement('div');
    daily.className = 'summary-grid';
    daily.innerHTML = `
      <div class="summary-card">
        <h4>TODAY'S DATE</h4>
        <div class="value">${summary.date || '-'}</div>
      </div>
      <div class="summary-card">
        <h4>DAILY BETS</h4>
        <div class="value">${summary.num_bets ?? '-'}</div>
        <div class="sub">Staked: ${summary.staked ?? '-'} | P/L: ${summary.profit ?? '-'}</div>
      </div>
      <div class="summary-card">
        <h4>DAILY ROI</h4>
        <div class="value">${formatPct(summary.roi_pct)}</div>
      </div>
      <div class="summary-card">
        <h4>CURRENT BANKROLL</h4>
        <div class="value">${summary.current_bankroll ?? '-'}</div>
      </div>
    `;
    wrapper.appendChild(daily);
  }

  // Overall performance block
  if (performance) {
    const perf = document.createElement('div');
    perf.className = 'summary-grid';
    perf.innerHTML = `
      <div class="summary-card">
        <h4>TOTAL BETS</h4>
        <div class="value">${performance.total_bets ?? '-'}</div>
        <div class="sub">
          Wins: ${performance.wins ?? '-'} |
          Losses: ${performance.losses ?? '-'} |
          Pushes: ${performance.pushes ?? '-'}
        </div>
      </div>
      <div class="summary-card">
        <h4>ALL-TIME STAKED</h4>
        <div class="value">${performance.total_staked ?? '-'}</div>
      </div>
      <div class="summary-card">
        <h4>ALL-TIME PROFIT</h4>
        <div class="value">${performance.total_profit ?? '-'}</div>
      </div>
      <div class="summary-card">
        <h4>ALL-TIME ROI</h4>
        <div class="value">${formatPct(performance.roi_pct)}</div>
        <div class="sub">Bankroll: ${performance.current_bankroll ?? '-'}</div>
      </div>
    `;
    wrapper.appendChild(perf);
  }

  container.appendChild(wrapper);
}

/* ---------- HELPERS ---------- */

function safePercent(evStr) {
  // evStr is something like "0.1514"
  const num = parseFloat(evStr);
  if (isNaN(num)) return 0;
  return Math.min(Math.max(num * 100, 0), 100);
}

function formatPct(v) {
  if (v === null || v === undefined || v === "") return "-";
  const num = Number(v);
  if (isNaN(num)) return v;
  return num.toFixed(1) + "%";
}

/* ------------------ GRAPHICS RENDERING ------------------------ */

function buildGraphics(performance, history) {
  renderROIGauge(performance);
  renderWinLoss(performance);
  renderBankroll(history);
}

/* ---- ROI Gauge ---- */

function renderROIGauge(perf) {
  const roi = Number(perf?.roi_pct ?? 0);
  const clamped = Math.max(-100, Math.min(roi, 100));

  // Convert -100..100 → 0..180 degrees
  const angle = ((clamped + 100) / 200) * 180;

  document.getElementById("roi-fill").style.transform =
    `rotate(${angle}deg)`;

  document.getElementById("roi-text").textContent = roi.toFixed(1) + "%";
}

/* ---- Win/Loss Donut ---- */

function renderWinLoss(perf) {
  const ctx = document.getElementById("winLossChart");

  new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Wins", "Losses", "Pushes"],
      datasets: [{
        data: [
          perf.wins ?? 0,
          perf.losses ?? 0,
          perf.pushes ?? 0
        ],
        backgroundColor: ["#4caf50", "#f44336", "#ff9800"],
        borderWidth: 0
      }]
    },
    options: {
      plugins: { legend: { labels: { color: "#ccc" } } },
      cutout: "60%"
    }
  });
}

/* ---- Bankroll Sparkline ---- */

function renderBankroll(history) {
  const ctx = document.getElementById("bankrollChart");

  const labels = history.map(h => h.date);
  const bankroll = history.map(h => Number(h.bankroll || 0));

  new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [{
        data: bankroll,
        borderColor: "#ff7a1c",
        backgroundColor: "rgba(255,122,28,0.2)",
        borderWidth: 2,
        tension: 0.25
      }]
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#666" }, grid: { color: "#222" } },
        y: { ticks: { color: "#ccc" }, grid: { color: "#222" } }
      }
    }
  });
}

