async function loadJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to load ${path}`);
  return res.json();
}

function formatCurrencyUnits(x) {
  if (x === null || x === undefined) return "--";
  const n = Number(x);
  const sign = n > 0 ? "+" : n < 0 ? "-" : "";
  return `${sign}${Math.abs(n).toFixed(2)} u`;
}

function formatBankroll(x) {
  return `${Number(x).toFixed(2)} u`;
}

async function init() {
  try {
    const [picks, bankrollHistory] = await Promise.all([
      loadJSON("data.json"),
      loadJSON("bankroll.json"),
    ]);

    // Last updated = now (local model run)
    const now = new Date();
    document.getElementById("last-updated").textContent =
      "Last update: " + now.toLocaleString();

    renderPicks(picks);
    renderBankroll(bankrollHistory);
    renderStats(picks, bankrollHistory);
  } catch (err) {
    console.error(err);
    const picksGrid = document.getElementById("picks-grid");
    picksGrid.innerHTML =
      "<p>Failed to load SmartPicks data. Check data.json / bankroll.json.</p>";
  }
}

function renderPicks(picks) {
  const container = document.getElementById("picks-grid");
  container.innerHTML = "";

  if (!picks || picks.length === 0) {
    container.innerHTML = "<p>No picks available.</p>";
    return;
  }

  for (const p of picks) {
    const card = document.createElement("div");
    card.className = "pick-card";

    const evClass =
      p.adjusted_ev > 0.01
        ? "ev-positive"
        : Math.abs(p.adjusted_ev) < 0.005
        ? "ev-neutral"
        : "";

    card.innerHTML = `
      <div class="pick-header">
        <span class="pick-rank">#${p.rank}</span>
        <div>
          <div class="pick-main">${p.team}</div>
          <div class="pick-market">${p.market.toUpperCase()} · ${p.sport ||
      ""}</div>
        </div>
      </div>
      <div class="pick-row"><strong>Match:</strong> ${p.match}</div>
      <div class="pick-row"><strong>Price:</strong> ${p.price}</div>
      <div class="pick-row"><strong>Adj EV:</strong> <span class="pick-ev ${evClass}">${p.adjusted_ev.toFixed(
      4
    )}</span></div>
      <div class="pick-reason">${p.reason}</div>
    `;

    container.appendChild(card);
  }
}

function renderBankroll(history) {
  const ctx = document.getElementById("bankrollChart");
  if (!history || history.length === 0 || !history[0].date) {
    ctx.getContext("2d").font = "12px sans-serif";
    ctx.getContext("2d").fillStyle = "#999";
    ctx.getContext("2d").fillText(
      "No bankroll history yet – wait for some settled bets.",
      8,
      30
    );
    document.getElementById(
      "bankroll-summary"
    ).textContent = "No settled bets yet.";
    return;
  }

  const labels = history.map((h) => h.date);
  const data = history.map((h) => h.bankroll);
  const start = data[0];
  const end = data[data.length - 1];
  const pnl = end - start;

  new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Bankroll (u)",
          data,
          tension: 0.25,
          borderWidth: 2,
          pointRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
      },
      scales: {
        x: {
          ticks: { color: "#9da4c4" },
          grid: { display: false },
        },
        y: {
          ticks: { color: "#9da4c4" },
          grid: { color: "rgba(80, 90, 130, 0.3)" },
        },
      },
    },
  });

  document.getElementById(
    "bankroll-summary"
  ).innerHTML = `Start: <span class="value">${formatBankroll(
    start
  )}</span> · Current: <span class="value">${formatBankroll(
    end
  )}</span> · P/L: <span class="value">${formatCurrencyUnits(pnl)}</span>`;
}

function renderStats(picks, history) {
  // Today stats: we can't fully reconstruct W/L from frontend,
  // so for now we just show "bets today" = picks.length
  document.getElementById("today-bets").textContent = picks.length;
  document.getElementById("today-record").textContent = "—";
  document.getElementById("today-units").textContent = `${(
    picks.length || 0
  ).toFixed(2)} u`;
  document.getElementById("today-profit").textContent = "—";

  // Overall stats from bankroll history
  if (!history || history.length === 0 || !history[0].date) {
    document.getElementById("overall-bankroll").textContent = "200.00 u";
    document.getElementById("overall-pl").textContent = "+0.00 u";
    document.getElementById("overall-lastday").textContent = "—";
    return;
  }

  const start = history[0].bankroll;
  const end = history[history.length - 1].bankroll;
  const pnl = end - start;

  document.getElementById("overall-bankroll").textContent =
    formatBankroll(end);
  document.getElementById("overall-pl").textContent = formatCurrencyUnits(pnl);

  if (history.length >= 2) {
    const prev = history[history.length - 2].bankroll;
    const dayChange = end - prev;
    document.getElementById("overall-lastday").textContent =
      formatCurrencyUnits(dayChange);
  } else {
    document.getElementById("overall-lastday").textContent = "—";
  }
}

init();

