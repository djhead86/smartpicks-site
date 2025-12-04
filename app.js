// SmartPicks Frontend for new backend schema
// Expects data.json = { generated, picks, history, analytics }

let GLOBAL_DATA = null;

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  loadData();
});

function setupTabs() {
  const buttons = document.querySelectorAll(".tab-button");
  const panels = document.querySelectorAll(".tab-panel");

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.dataset.target;

      buttons.forEach((b) => b.classList.remove("active"));
      panels.forEach((p) => p.classList.remove("active"));

      btn.classList.add("active");
      const panel = document.getElementById(targetId);
      if (panel) panel.classList.add("active");
    });
  });
}

function loadData() {
  /* =======================
   LIVE SCORE TICKER
======================= */
async function fetchLiveScores() {
    try {
        const sports = ["basketball_nba", "americanfootball_nfl", "soccer_epl"];

        // Grab events WE actually have bets on:
        const response = await fetch("data.json");
        const data = await response.json();
        const openEvents = (data.history || [])
            .filter(row => row.status === "OPEN")
            .map(row => row.event);
        // After you parse data.json:
        const openBets = data.history.filter(r => r.status === "OPEN");
            renderGrader(openBets);


        let tickerItems = [];

        for (const sport of sports) {
            const url = `https://api.the-odds-api.com/v4/sports/${sport}/scores?apiKey=${ODDS_API_KEY}&daysFrom=2`;

            const res = await fetch(url);
            if (!res.ok) continue;
            const scores = await res.json();

            for (const game of scores) {
                const match = game.teams ? `${game.teams[0]} @ ${game.teams[1]}` : "";

                // Only show scores for games we bet on
                if (!openEvents.some(ev => ev.includes(game.teams?.[1]) || ev.includes(game.teams?.[0]))) {
                    continue;
                }

                const home = game.home_score;
                const away = game.away_score;

                let status = game.completed
                    ? "FINAL"
                    : (game.time || "LIVE");

                tickerItems.push(
                    `${game.teams[0]} ${away} – ${home} ${game.teams[1]} (${status})`
                );
            }
        }

        const ticker = document.getElementById("score-ticker");
        if (tickerItems.length === 0) {
            ticker.innerHTML = `<span>No live games right now</span>`;
        } else {
            ticker.innerHTML = tickerItems.map(t => `<span>${t}</span>`).join("");
        }

    } catch (err) {
        console.error("Score ticker error:", err);
    }
}

/* Refresh ticker every 60sec */
setInterval(fetchLiveScores, 60000);
fetchLiveScores();

  fetch("data.json")
    .then((r) => {
      if (!r.ok) {
        throw new Error(`HTTP ${r.status}`);
      }
      return r.json();
    })
    .then((data) => {
      GLOBAL_DATA = data;
      renderAll(data);
    })
    .catch((err) => {
      console.error("Failed to load data.json:", err);
      setErrorState(err);
    });
}

function setErrorState(err) {
  const msg = `Failed to load data: ${err}`;
  ["summary", "picks", "history", "analytics"].forEach((id) => {
    const panel = document.getElementById(id);
    if (panel) {
      panel.innerHTML = `<p class="loading">${msg}</p>`;
    }
  });
}

// ---------- Render entry point ----------

function renderAll(data) {
  const generated = data.generated || "";
  const picks = data.open_bets || [];
  const history = data.history || [];
  const analytics = data.analytics || {
    total_bets: 0,
    wins: 0,
    losses: 0,
    pushes: 0,
    roi: 0,
    sport_roi: {},
    bankroll_history: []
  };

  const lastUpdatedEl = document.getElementById("last-updated");
  if (lastUpdatedEl) {
    lastUpdatedEl.textContent = generated
      ? `Last updated: ${generated}`
      : "Last updated: (unknown)";
  }

  renderSummaryTab(picks, history, analytics);
  renderPicksTab(picks);
  renderHistoryTab(history);
  renderAnalyticsTab(analytics);
}

// ---------- Score Fetch Helper ----------




// ---------- Summary Tab ----------

function renderSummaryTab(picks, history, analytics) {
  const sec = document.getElementById("summary");
  if (!sec) return;

  const openCount = history.filter(
    (r) => (r.status || "").toUpperCase() === "OPEN" || (r.result || "").toUpperCase() === "PENDING"
  ).length;

  const closedCount = analytics.total_bets || history.length || 0;
  const roiPct = (analytics.roi || 0) * 100;

  sec.innerHTML = `
    <div class="summary-grid">
      <div class="card">
        <h3>Total Bets</h3>
        <div class="value">${closedCount}</div>
        <div class="sub">All-time graded bets</div>
      </div>
      <div class="card">
        <h3>Open / Pending</h3>
        <div class="value">${openCount}</div>
        <div class="sub">Active tickets in bet_history.csv</div>
      </div>
      <div class="card">
        <h3>Today's Picks</h3>
        <div class="value">${picks.length}</div>
        <div class="sub">New value opportunities</div>
      </div>
      <div class="card">
        <h3>ROI</h3>
        <div class="value">${roiPct.toFixed(2)}%</div>
        <div class="sub">Aggregate return on invested units</div>
      </div>
    </div>
  `;
}

// ---------- Picks Tab ----------

function renderPicksTab(picks) {
  const sec = document.getElementById("picks");
  if (!sec) return;

  if (!picks.length) {
    sec.innerHTML = `<p class="loading">No current picks. Run smart_picks.py to generate fresh edges.</p>`;
    return;
  }

  // Sort by event_time if available
  const sorted = [...picks].sort((a, b) => {
    const ta = a.event_time || "";
    const tb = b.event_time || "";
    return ta.localeCompare(tb);
  });

  const cardsHtml = sorted
    .map((p) => {
      const ev = Number(p.ev || 0);
      const evBadgeClass = ev >= 0 ? "badge badge-ev-pos" : "badge badge-ev-neg";
      const evLabel = ev >= 0 ? `+${ev.toFixed(3)}` : ev.toFixed(3);

      const implied = Number(p.implied_prob || 0) * 100;
      const model = Number(p.model_prob || 0) * 100;
      const edge = model - implied;

      return `
        <article class="pick-card">
          <div class="pick-header">
            <h2>${p.team}</h2>
            <span class="${evBadgeClass}">EV ${evLabel}</span>
          </div>
          <div class="pick-match">${p.match} • ${p.sport}</div>
          <div class="pick-meta">
            <span>Market: ${p.market}</span>
            <span>Odds: ${formatOdds(p.price)}</span>
            <span>Stake: $${Number(p.recommended_stake || 0).toFixed(2)}</span>
          </div>
          <div class="pick-meta">
            <span>Model: ${model.toFixed(1)}%</span>
            <span>Implied: ${implied.toFixed(1)}%</span>
            <span>Edge: ${edge.toFixed(1)} pts</span>
          </div>
          <div class="pick-meta">
            <span>Event time: ${p.event_time || "—"}</span>
          </div>
        </article>
      `;
    })
    .join("");

  sec.innerHTML = `
    <div class="picks-list">
      ${cardsHtml}
    </div>
  `;
}

function renderGrader(openBets) {
  const container = document.getElementById("grader-root");
  if (!container) return;

  if (!openBets.length) {
    container.innerHTML = "<p>No open bets to grade.</p>";
    return;
  }

  const rows = openBets.map(bet => {
    const id = bet.bet_id || bet.betId || ""; // depending which you stored
    return `
      <tr>
        <td>${bet.date || ""}</td>
        <td>${bet.sport}</td>
        <td>${bet.event}</td>
        <td>${bet.team} (${bet.market})</td>
        <td>${bet.odds}</td>
        <td>
          <button data-id="${id}" data-outcome="win">Win</button>
          <button data-id="${id}" data-outcome="loss">Loss</button>
          <button data-id="${id}" data-outcome="push">Push</button>
        </td>
      </tr>`;
  }).join("");

  container.innerHTML = `
    <table class="table">
      <thead>
        <tr>
          <th>Date</th><th>Sport</th><th>Event</th><th>Side</th><th>Odds</th><th>Grade</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;

  container.querySelectorAll("button[data-id]").forEach(btn => {
    btn.addEventListener("click", () => {
      const betId = btn.getAttribute("data-id");
      const outcome = btn.getAttribute("data-outcome");
      fetch("http://127.0.0.1:5001/grade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bet_id: betId, outcome })
      })
      .then(r => r.json())
      .then(resp => {
        if (resp.status === "ok") {
          alert(`Graded ${betId} as ${outcome.toUpperCase()}. Refreshing...`);
          window.location.reload();
        } else {
          alert("Error grading bet: " + (resp.message || "unknown"));
        }
      })
      .catch(err => {
        console.error(err);
        alert("Failed to talk to local grader API. Is grader_api.py running?");
      });
    });
  });
}


function formatOdds(o) {
  const n = Number(o || 0);
  if (Number.isNaN(n)) return String(o);
  return n > 0 ? `+${n}` : `${n}`;
}

// ---------- History Tab ----------

function renderHistoryTab(history) {
  const sec = document.getElementById("history");
  if (!sec) return;

  if (!history.length) {
    sec.innerHTML = `<p class="loading">No history yet. Once bets are generated and tracked, they will show here.</p>`;
    return;
  }

  const rowsHtml = history
    .map((r) => {
      const status = (r.status || "").toUpperCase();
      const result = (r.result || "").toUpperCase();

      const statusClass =
        status === "OPEN" ? "status-open" : status === "CLOSED" ? "status-closed" : "";
      let resultClass = "";
      if (result === "WIN") resultClass = "result-win";
      else if (result === "LOSS") resultClass = "result-loss";
      else if (result === "PUSH") resultClass = "result-push";

      return `
        <tr>
          <td>${r.date || ""}</td>
          <td>${r.sport || ""}</td>
          <td>${r.match || ""}</td>
          <td>${r.team || ""} (${r.market || ""})</td>
          <td>${formatOdds(r.odds)}</td>
          <td>$${Number(r.stake || 0).toFixed(2)}</td>
          <td class="${statusClass}">${status || ""}</td>
          <td class="${resultClass}">${result || ""}</td>
          <td>${Number(r.profit || 0).toFixed(2)}</td>
          <td>${r.bankroll_after || ""}</td>
        </tr>
      `;
    })
    .join("");

  sec.innerHTML = `
    <div class="history-table-wrapper">
      <table class="history-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Sport</th>
            <th>Event</th>
            <th>Side</th>
            <th>Odds</th>
            <th>Stake</th>
            <th>Status</th>
            <th>Result</th>
            <th>Profit</th>
            <th>Bankroll</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    </div>
  `;
}

// ---------- Analytics Tab ----------

function renderAnalyticsTab(analytics) {
  const sec = document.getElementById("analytics");
  if (!sec) return;

  const total = analytics.total_bets || 0;
  const wins = analytics.wins || 0;
  const losses = analytics.losses || 0;
  const pushes = analytics.pushes || 0;
  const roi = (analytics.roi || 0) * 100;

  const sportRoi = analytics.sport_roi || {};
  const bankrollHist = analytics.bankroll_history || [];

  const winPct = total > 0 ? (wins / total) * 100 : 0;

  // Summary cards
  const summaryHtml = `
    <div class="analytics-grid">
      <div class="card">
        <h3>Total Bets</h3>
        <div class="value">${total}</div>
        <div class="sub">All-time tracked bets</div>
      </div>
      <div class="card">
        <h3>Record</h3>
        <div class="value">${wins}-${losses}-${pushes}</div>
        <div class="sub">Win rate: ${winPct.toFixed(1)}%</div>
      </div>
      <div class="card">
        <h3>ROI</h3>
        <div class="value">${roi.toFixed(2)}%</div>
        <div class="sub">Return on total stake</div>
      </div>
      <div class="card">
        <h3>Sports Tracked</h3>
        <div class="value">${Object.keys(sportRoi).length}</div>
        <div class="sub">Distinct markets with bets</div>
      </div>
    </div>
  `;

  // Bankroll chart container
  const chartHtml = `
    <div id="bankroll-chart-container">
      <h3 style="font-size:0.9rem; color:#9ca3af; margin-bottom:0.5rem;">Bankroll Over Time</h3>
      <canvas id="bankroll-chart" height="120"></canvas>
    </div>
  `;

  // ROI by sport
  const roiRows = Object.entries(sportRoi)
    .map(([sport, v]) => {
      const pct = (Number(v) * 100).toFixed(2);
      return `
        <div class="sport-roi-row">
          <span>${sport}</span>
          <span>${pct}%</span>
        </div>
      `;
    })
    .join("");

  const sportRoiHtml = `
    <div class="sport-roi-list">
      <h3 style="font-size:0.9rem; color:#9ca3af; margin-bottom:0.5rem;">ROI by Sport</h3>
      ${roiRows || `<p class="loading">No sport-level stats yet.</p>`}
    </div>
  `;

  sec.innerHTML = summaryHtml + chartHtml + sportRoiHtml;

  renderBankrollChart(bankrollHist);
}

function renderBankrollChart(history) {
  if (!history || !history.length) return;
  const canvas = document.getElementById("bankroll-chart");
  if (!canvas) return;

  const labels = history.map((p, idx) => p.t || `#${idx + 1}`);
  const values = history.map((p) => Number(p.bankroll || 0));

  const ctx = canvas.getContext("2d");
  new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Bankroll",
          data: values,
          borderWidth: 2,
          fill: false
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          ticks: {
            maxRotation: 45,
            minRotation: 0
          }
        }
      }
    }
  });
}
