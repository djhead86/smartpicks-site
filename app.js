// SmartPicksGPT Cyberpunk Dashboard Logic

const DATA_URL = "data/data.json";

document.addEventListener("DOMContentLoaded", () => {
  loadDashboard().catch((err) => {
    console.error("Dashboard error:", err);
    const statusEls = [
      document.getElementById("overview-status"),
      document.getElementById("top-picks-status"),
      document.getElementById("daily-status"),
    ].filter(Boolean);

    statusEls.forEach((el) => {
      el.textContent = "Failed to load data.json – check GitHub Pages build.";
      el.classList.add("status-error");
    });
  });
});

async function loadDashboard() {
  setLastUpdatedNow();

  const res = await fetch(`${DATA_URL}?t=${Date.now()}`);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }

  const data = await res.json();

  const top10 = Array.isArray(data.top10) ? data.top10 : [];
  const daily = data.daily_summary || {};
  const perf = data.performance || {};
  const history = Array.isArray(data.history) ? data.history : [];

  renderOverview(perf);
  renderDailySummary(daily);
  renderTopPicks(top10);
  renderHistory(history);
}

/* ---------- UTILITIES ---------- */

function setLastUpdatedNow() {
  const el = document.getElementById("last-updated");
  if (!el) return;
  const now = new Date();
  el.textContent = now.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function asNumber(value, fallback = 0) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function formatCurrency(value) {
  const num = asNumber(value, 0);
  return `$${num.toFixed(2)}`;
}

function formatPercent(value) {
  const num = asNumber(value, 0);
  return `${num.toFixed(1)}%`;
}

function formatPercentFromFraction(value) {
  const num = asNumber(value, 0) * 100;
  return `${num.toFixed(1)}%`;
}

function formatMoneyline(price) {
  const num = asNumber(price, NaN);
  if (!Number.isFinite(num)) return "—";
  if (num > 0) return `+${num}`;
  return `${num}`;
}

function formatSportCode(code) {
  if (!code) return "—";
  return code.replace(/_/g, " ").toUpperCase();
}

function formatMarketLabel(market) {
  switch (market) {
    case "h2h":
      return "Moneyline";
    case "spreads":
      return "Spread";
    case "totals":
      return "Over / Under";
    default:
      return market || "Unknown";
  }
}

function formatDateTimeShort(dtString) {
  if (!dtString) return "—";
  const d = new Date(dtString.replace(" ", "T") + "Z");
  if (isNaN(d.getTime())) return dtString;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDateOnly(dtString) {
  if (!dtString) return "—";
  const d = new Date(dtString.replace(" ", "T") + "Z");
  if (isNaN(d.getTime())) return dtString;
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "2-digit",
    year: "numeric",
  });
}

/* ---------- OVERVIEW / PERFORMANCE ---------- */

function renderOverview(perf) {
  const statusEl = document.getElementById("overview-status");
  if (!perf || Object.keys(perf).length === 0) {
    if (statusEl) {
      statusEl.textContent = "No lifetime performance data yet. Once bets settle, stats will appear here.";
      statusEl.classList.remove("status-error");
      statusEl.classList.add("status-muted");
    }
    setText("kpi-bankroll", "$0.00");
    setText("kpi-total-profit", "$0.00");
    setText("kpi-roi", "0.0%");
    setText("perf-total-bets", "0");
    setText("perf-wins", "0");
    setText("perf-losses", "0");
    setText("perf-pushes", "0");
    setText("perf-total-staked", "$0.00");
    return;
  }

  if (statusEl) statusEl.textContent = "";

  const bankroll = asNumber(perf.current_bankroll);
  const totalProfit = asNumber(perf.total_profit);
  const roiPct = asNumber(perf.roi_pct);
  const totalBets = asNumber(perf.total_bets);
  const wins = asNumber(perf.wins);
  const losses = asNumber(perf.losses);
  const pushes = asNumber(perf.pushes);
  const totalStaked = asNumber(perf.total_staked);

  setText("kpi-bankroll", formatCurrency(bankroll));
  setText("kpi-total-profit", formatCurrency(totalProfit));
  setText("kpi-roi", formatPercent(roiPct));

  setText("perf-total-bets", totalBets.toString());
  setText("perf-wins", wins.toString());
  setText("perf-losses", losses.toString());
  setText("perf-pushes", pushes.toString());
  setText("perf-total-staked", formatCurrency(totalStaked));
}

/* ---------- DAILY SUMMARY ---------- */

function renderDailySummary(daily) {
  const statusEl = document.getElementById("daily-status");
  const datePill = document.getElementById("daily-date-pill");

  if (!daily || Object.keys(daily).length === 0) {
    if (statusEl) {
      statusEl.textContent = "No bets placed in the current daily window.";
      statusEl.classList.remove("status-error");
      statusEl.classList.add("status-muted");
    }
    if (datePill) datePill.textContent = "No session";
    setText("daily-bets", "0");
    setText("daily-staked", "$0.00");
    setText("daily-profit", "$0.00");
    setText("daily-roi", "0.0%");
    setText("daily-bankroll", "$0.00");
    return;
  }

  if (statusEl) statusEl.textContent = "";
  if (datePill) {
    const d = daily.date || "";
    datePill.textContent = d || "Today";
  }

  const numBets = asNumber(daily.num_bets);
  const staked = asNumber(daily.staked);
  const profit = asNumber(daily.profit);
  const roiPct = asNumber(daily.roi_pct);
  const br = asNumber(daily.current_bankroll);

  setText("daily-bets", numBets.toString());
  setText("daily-staked", formatCurrency(staked));
  setText("daily-profit", formatCurrency(profit));
  setText("daily-roi", formatPercent(roiPct));
  setText("daily-bankroll", formatCurrency(br));
}

/* ---------- TOP PICKS ---------- */

function renderTopPicks(top10) {
  const listEl = document.getElementById("top-picks-list");
  const statusEl = document.getElementById("top-picks-status");

  if (!listEl) return;

  if (!Array.isArray(top10) || top10.length === 0) {
    listEl.innerHTML = `
      <div class="empty-state mono">
        No model-positive edges in the next 24 hours. Check back after the next refresh.
      </div>
    `;
    if (statusEl) statusEl.textContent = "";
    return;
  }

  if (statusEl) statusEl.textContent = "";

  const html = top10
    .map((pick, idx) => {
      const rank = idx + 1;
      const sport = formatSportCode(pick.sport);
      const match = pick.match || "Unknown matchup";
      const team = pick.team || "Unknown side";
      const market = pick.market || "h2h";
      const marketLabel = formatMarketLabel(market);
      const oddsStr = formatMoneyline(pick.price);
      const probPct = formatPercentFromFraction(pick.prob);
      const adjEv = asNumber(pick.adj_ev);
      const kelly = asNumber(pick.kelly);
      const stake = asNumber(pick.recommended_stake);
      const expProfit = asNumber(pick.expected_profit);
      const time = formatDateTimeShort(pick.event_time);

      return `
        <article class="pick-card">
          <div class="pick-rank mono">#${rank.toString().padStart(2, "0")}</div>
          <div>
            <div class="pick-header">
              <div class="pick-match mono">${escapeHtml(match)}</div>
              <div class="pick-odds mono">${oddsStr}</div>
            </div>
            <div class="pick-meta-row">
              <span class="pick-team mono">${escapeHtml(team)}</span>
              <span class="pick-market mono">${marketLabel}</span>
              <span class="pick-sport mono">${sport}</span>
              <span class="pick-time mono">⏱ ${time}</span>
            </div>
            <div class="pick-metrics-row mono">
              <span class="pick-prob">
                Hit prob: <strong>${probPct}</strong>
              </span>
              <span class="pick-ev">
                Adj. EV: <strong>${expProfit.toFixed(2)}u</strong>
              </span>
              <span>
                Kelly: <strong>${(kelly * 100).toFixed(2)}%</strong>
              </span>
              <span>
                Stake: <strong>${stake.toFixed(2)}u</strong>
              </span>
            </div>
          </div>
        </article>
      `;
    })
    .join("");

  listEl.innerHTML = html;
}

/* ---------- HISTORY TABLE ---------- */

function renderHistory(history) {
  const tbody = document.getElementById("history-body");
  if (!tbody) return;

  if (!Array.isArray(history) || history.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="11" class="empty-row">
          <span class="mono empty-state">No graded tickets yet. Once results settle, they will show up here.</span>
        </td>
      </tr>
    `;
    return;
  }

  const rows = history.slice(-50).map((bet) => {
    const date = bet.date || "";
    const sport = formatSportCode(bet.sport);
    const match = bet.match || "";
    const team = bet.team || "";
    const market = formatMarketLabel(bet.market);
    const odds = formatMoneyline(bet.price);
    const stake = formatCurrency(bet.stake || bet.units || 0);
    const ev = formatCurrency(bet.expected_profit ?? bet.expected_value ?? 0);
    const result = (bet.result || "PENDING").toUpperCase();
    const actualProfit = formatCurrency(bet.actual_profit ?? bet.profit ?? 0);
    const bankroll = bet.bankroll_after ?? bet.bankroll ?? "";
    const bankrollDisplay = bankroll === "" ? "—" : formatCurrency(bankroll);

    const resultClass =
      result === "WIN"
        ? "result-win"
        : result === "LOSS"
        ? "result-loss"
        : result === "PUSH"
        ? "result-push"
        : "result-pending";

    return `
      <tr>
        <td class="mono">${escapeHtml(date)}</td>
        <td class="mono">${sport}</td>
        <td class="mono">${escapeHtml(match)}</td>
        <td class="mono">${escapeHtml(team)}</td>
        <td class="mono">${market}</td>
        <td class="mono">${odds}</td>
        <td class="mono">${stake}</td>
        <td class="mono">${ev}</td>
        <td class="mono">
          <span class="result-pill ${resultClass}">${result}</span>
        </td>
        <td class="mono">${actualProfit}</td>
        <td class="mono">${bankrollDisplay}</td>
      </tr>
    `;
  });

  tbody.innerHTML = rows.join("");
}

/* ---------- DOM HELPERS ---------- */

function setText(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = value;
}

function escapeHtml(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
