// SmartPicksGPT v2 frontend
// Fully wired to current data.json schema and adds EV, edge, exposure, charts

const DATA_URL = `data/data.json?ts=${Date.now()}`;

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  loadData();
});

/* ========= TAB SYSTEM ========= */

function setupTabs() {
  const buttons = document.querySelectorAll(".tab-button");
  const sections = document.querySelectorAll(".tab-content");

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-tab");

      buttons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      sections.forEach((sec) =>
        sec.classList.toggle("active", sec.id === target)
      );
    });
  });
}

/* ========= LOAD & ENRICH DATA ========= */

async function loadData() {
  try {
    const res = await fetch(DATA_URL, { cache: "no-store" });
    const raw = await res.json();

    const data = enrichData(raw);

    renderSummaryTab(data);
    renderPicksTab(data);
    renderAnalyticsTab(data);
    renderHistoryTab(data);
    setLastUpdated(data.last_updated);
  } catch (err) {
    console.error("Failed to load data.json", err);
    const summary = document.getElementById("summary");
    if (summary) {
      summary.innerHTML =
        "<p class='muted'>Failed to load SmartPicks data.json.</p>";
    }
  }
}

/**
 * Enrich the backend JSON with:
 * - implied probability, decimal odds, EV, edge, confidence
 * - pick groups (by game)
 * - exposure by sport & market
 */
function enrichData(data) {
  const clone = structuredClone(data);

  const picks = clone.todays_picks || [];
  const open = clone.open_bets || [];

  // ---- Enrich picks with EV + edge + implied prob + confidence ----
  const pickGroups = {};
  picks.forEach((p) => {
    const oddsNum = toNumber(p.odds);
    const dec = americanToDecimal(oddsNum);
    const implied = impliedProbFromAmerican(oddsNum);
    const winProb = isFinite(p.win_probability)
      ? p.win_probability
      : null;

    let edge = null;
    let evUnits = null;
    if (winProb !== null && isFinite(dec) && dec > 1) {
      edge = winProb - implied;
      evUnits = winProb * (dec - 1) - (1 - winProb);
    }

    p._decimal_odds = dec;
    p._implied_prob = implied;
    p._edge = edge;
    p._ev_units = evUnits;
    p._confidence = computeConfidence(p.score, edge);

    const key = `${p.sport || "unknown"}__${p.event || "Unknown Event"}`;
    if (!pickGroups[key]) {
      pickGroups[key] = {
        sport: p.sport || "unknown",
        event: p.event || "Unknown Event",
        game_time: p.game_time || "TBD",
        picks: [],
      };
    }
    pickGroups[key].picks.push(p);
  });

  clone._pick_groups = Object.values(pickGroups);

  // ---- Enrich open bets with implied prob + payout ----
  let totalStakeOpen = 0;
  const sportRisk = {};
  const marketMix = {};

  open.forEach((b) => {
    const stake = toNumber(b.bet_amount);
    const oddsNum = toNumber(b.odds);
    const dec = americanToDecimal(oddsNum);
    const implied = impliedProbFromAmerican(oddsNum);

    totalStakeOpen += stake;

    const sportKey = b.sport || "unknown";
    sportRisk[sportKey] = (sportRisk[sportKey] || 0) + stake;

    const mktKey = b.market || "other";
    marketMix[mktKey] = (marketMix[mktKey] || 0) + 1;

    b._decimal_odds = dec;
    b._implied_prob = implied;
    b._potential_payout =
      isFinite(dec) && dec > 0 ? stake * dec : null;
  });

  clone._total_stake_open = totalStakeOpen;
  clone._sport_risk = sportRisk;
  clone._market_mix = marketMix;

  return clone;
}

/* ========= MATH HELPERS ========= */

function toNumber(v, fallback = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function americanToDecimal(odds) {
  if (!Number.isFinite(odds) || odds === 0) return null;
  if (odds > 0) return 1 + odds / 100;
  return 1 + 100 / Math.abs(odds);
}

function impliedProbFromAmerican(odds) {
  if (!Number.isFinite(odds) || odds === 0) return 0;
  if (odds > 0) {
    return 100 / (odds + 100);
  }
  return Math.abs(odds) / (Math.abs(odds) + 100);
}

function formatAmericanOdds(price) {
  if (!Number.isFinite(price)) return "—";
  return price > 0 ? `+${price}` : `${price}`;
}

function formatPct(x) {
  if (!Number.isFinite(x)) return "—";
  return `${(x * 100).toFixed(1)}%`;
}

function formatMoney(x) {
  if (!Number.isFinite(x)) return "—";
  return x >= 0 ? `+$${x.toFixed(2)}` : `-$${Math.abs(x).toFixed(2)}`;
}

function normalizeSport(sport) {
  const map = {
    basketball_nba: "NBA",
    americanfootball_nfl: "NFL",
    icehockey_nhl: "NHL",
    soccer_epl: "EPL",
  };
  return map[sport] || (sport ? sport.toUpperCase() : "Unknown");
}

function normalizeMarket(m) {
  const map = {
    h2h: "Moneyline",
    spreads: "Spread",
    totals: "Over/Under",
  };
  return map[m] || (m ? m.toUpperCase() : "—";
}

function classifyScoreBadge(score) {
  if (!Number.isFinite(score)) return "badge-ev-neutral";
  if (score > 0.05) return "badge-ev-positive";
  if (score < -0.01) return "badge-ev-negative";
  return "badge-ev-neutral";
}

/**
 * Very simple "confidence" heuristic:
 * combines model score + edge into 1–5.
 */
function computeConfidence(score, edge) {
  if (!Number.isFinite(score)) score = 0;
  if (!Number.isFinite(edge)) edge = 0;

  const sNorm = (score - 0.75) / 0.1; // rough
  const eNorm = edge / 0.05; // 5% edge is big
  let c = (sNorm + eNorm) / 2;
  c = Math.max(0, Math.min(1.5, c));

  const scaled = 1 + c * 4; // 1–5
  return Math.round(scaled);
}

/* ========= SUMMARY TAB ========= */

function renderSummaryTab(data) {
  const section = document.getElementById("summary");
  if (!section) return;

  const stats = data.stats || {};
  const streak = data.streak || {};

  const bankroll = data.bankroll ?? 0;
  const totalBets = stats.total_bets || 0;
  const winPct = stats.win_pct || 0;
  const roi = stats.roi || 0;

  const currentStreak = streak.current ?? 0;
  const bestStreak = streak.best ?? 0;

  const openCount = (data.open_bets || []).length;
  const totalStakeOpen = data._total_stake_open || 0;

  const streakLabel =
    currentStreak > 0
      ? `W${currentStreak}`
      : currentStreak < 0
      ? `L${Math.abs(currentStreak)}`
      : "Even";

  const sportRiskEntries = Object.entries(data._sport_risk || {}).sort(
    (a, b) => b[1] - a[1]
  );

  section.innerHTML = `
    <div class="section-title">Bankroll & Engine Snapshot</div>

    <div class="summary-grid">
      <div class="metric-card">
        <div class="metric-label">Bankroll</div>
        <div class="metric-value">$${bankroll.toFixed(2)}</div>
        <div class="metric-sub">Live bankroll from engine</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">Total Bets Tracked</div>
        <div class="metric-value">${totalBets}</div>
        <div class="metric-sub">Win rate: ${formatPct(winPct)}</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">Lifetime ROI</div>
        <div class="metric-value">${formatPct(roi)}</div>
        <div class="metric-sub">Based on graded bets only</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">Current Streak</div>
        <div class="metric-value">${streakLabel}</div>
        <div class="metric-sub">Best streak: W${bestStreak}</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">Open Bets</div>
        <div class="metric-value">${openCount}</div>
        <div class="metric-sub">Total stake: $${totalStakeOpen.toFixed(2)}</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">Engine State</div>
        <div class="metric-value">${
          data.new_picks_generated ? "New picks ✅" : "No new picks"
        }</div>
        <div class="metric-sub">
          SmartPicksGPT grades results, updates bankroll, and proposes a small set of value plays.
        </div>
      </div>
    </div>

    ${
      sportRiskEntries.length
        ? `
    <div class="section-title" style="margin-top:20px;">Risk by Sport (Open Bets)</div>
    <div class="summary-grid">
      ${sportRiskEntries
        .slice(0, 4)
        .map(
          ([sport, stake]) => `
        <div class="metric-card metric-card-compact">
          <div class="metric-label">${normalizeSport(sport)}</div>
          <div class="metric-value">$${stake.toFixed(2)}</div>
          <div class="metric-sub">Open stake</div>
        </div>
      `
        )
        .join("")}
    </div>
    `
        : ""
    }

    <div class="summary-blurb">
      SmartPicksGPT is an experimental, disciplined betting engine. It is designed to
      keep bet sizing small, focus on EV-positive spots, and control volatility.
      This dashboard surfaces edge, exposure, and risk profiles from the underlying JSON.
    </div>
  `;
}

/* ========= PICKS TAB ========= */

function renderPicksTab(data) {
  const section = document.getElementById("picks");
  if (!section) return;

  const groups = data._pick_groups || [];
  if (!groups.length) {
    section.innerHTML = `
      <p class="muted">
        No SmartPicks for the current slate. When the engine generates new value plays,
        they will appear here grouped by game.
      </p>`;
    return;
  }

  // Sort groups by earliest game time
  groups.sort((a, b) => {
    const ta = new Date(a.game_time || 0).getTime();
    const tb = new Date(b.game_time || 0).getTime();
    return ta - tb;
  });

  section.innerHTML = `
    <div class="section-title">Today’s SmartPicks (Grouped by Game)</div>
    <div class="picks-grid">
      ${groups
        .map((g) => renderPickGroupCard(g))
        .join("")}
    </div>
  `;
}

function renderPickGroupCard(group) {
  const when = group.game_time || "TBD";
  const sportLabel = normalizeSport(group.sport);

  // Sort picks in this game by score descending
  const picks = [...group.picks].sort((a, b) => b.score - a.score);

  return `
    <article class="pick-card pick-group-card">
      <header class="pick-group-header">
        <div>
          <div class="pick-main">${group.event}</div>
          <div class="pick-match">${sportLabel} &bull; ${when}</div>
        </div>
        <div class="pick-group-tag">SmartPicks Stack</div>
      </header>

      <div class="pick-rows">
        ${picks.map(renderPickRow).join("")}
      </div>
    </article>
  `;
}

function renderPickRow(p) {
  const oddsNum = toNumber(p.odds);
  const implied = p._implied_prob;
  const winProb = p.win_probability;
  const edge = p._edge;
  const evUnits = p._ev_units;
  const confidence = p._confidence;

  const confidenceLabel = "★".repeat(confidence || 1);

  return `
    <div class="pick-row">
      <div class="pick-row-main">
        <div>
          <div class="pick-row-title">
            ${p.team} (${normalizeMarket(p.market)}) ${p.line != null ? `@ ${p.line}` : ""}
          </div>
          <div class="pick-row-sub">
            Odds ${formatAmericanOdds(oddsNum)} &bull;
            Model win: ${formatPct(winProb)} &bull;
            Implied: ${formatPct(implied)}
          </div>
        </div>
        <div class="pick-row-right">
          <span class="confidence-pill">Conf: ${confidenceLabel}</span>
        </div>
      </div>

      <div class="pick-row-meta">
        <span class="badge ${
          classifyScoreBadge(edge || 0)
        }">Edge: ${Number.isFinite(edge) ? (edge * 100).toFixed(1) + "%" : "—"}</span>
        <span class="badge badge-price">
          EV (1u): ${
            Number.isFinite(evUnits) ? evUnits.toFixed(3) + "u" : "—"
          }
        </span>
        <span class="badge badge-sport">Score: ${p.score.toFixed(4)}</span>
      </div>
    </div>
  `;
}

/* ========= ANALYTICS TAB ========= */

let stakeBySportChart = null;
let marketMixChart = null;

function renderAnalyticsTab(data) {
  const sportRisk = data._sport_risk || {};
  const marketMix = data._market_mix || {};

  const sportCanvas = document.getElementById("chartStakeBySport");
  const marketCanvas = document.getElementById("chartMarketMix");

  // --- Risk by sport (bar chart) ---
  if (sportCanvas && Object.keys(sportRisk).length) {
    const labels = Object.keys(sportRisk).map((s) => normalizeSport(s));
    const values = Object.values(sportRisk);

    if (stakeBySportChart) {
      stakeBySportChart.destroy();
    }

    stakeBySportChart = new Chart(sportCanvas.getContext("2d"), {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Open Stake ($)",
            data: values,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            display: false,
          },
        },
        scales: {
          x: {
            ticks: { color: "#cbd5f5" },
          },
          y: {
            ticks: { color: "#cbd5f5" },
            beginAtZero: true,
          },
        },
      },
    });

    const legendEl = document.getElementById("sport-legend");
    if (legendEl) {
      legendEl.innerHTML = labels
        .map(
          (label, idx) => `
        <div class="small-metric">
          <strong>${label}</strong><br />
          $${values[idx].toFixed(2)} open
        </div>
      `
        )
        .join("");
    }
  } else {
    const legendEl = document.getElementById("sport-legend");
    if (legendEl) {
      legendEl.innerHTML =
        "<span class='muted'>No open bets to chart.</span>";
    }
  }

  // --- Market mix (pie chart) ---
  if (marketCanvas && Object.keys(marketMix).length) {
    const labels = Object.keys(marketMix).map((m) => normalizeMarket(m));
    const values = Object.values(marketMix);

    if (marketMixChart) {
      marketMixChart.destroy();
    }

    marketMixChart = new Chart(marketCanvas.getContext("2d"), {
      type: "pie",
      data: {
        labels,
        datasets: [
          {
            data: values,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            labels: {
              color: "#cbd5f5",
            },
          },
        },
      },
    });

    const legendEl = document.getElementById("market-legend");
    if (legendEl) {
      legendEl.innerHTML = labels
        .map(
          (label, idx) => `
        <div class="small-metric">
          <strong>${label}</strong><br />
          ${values[idx]} open bet(s)
        </div>
      `
        )
        .join("");
    }
  } else {
    const legendEl = document.getElementById("market-legend");
    if (legendEl) {
      legendEl.innerHTML =
        "<span class='muted'>No open bets to chart.</span>";
    }
  }
}

/* ========= HISTORY / OPEN BETS TAB ========= */

function renderHistoryTab(data) {
  const section = document.getElementById("history");
  if (!section) return;

  const open = data.open_bets || [];

  if (!open.length) {
    section.innerHTML = `
      <div class="section-title">Open Bets</div>
      <p class="muted">No open bets right now. Once smart_picks.py places new wagers,
      they will appear here until graded.</p>
    `;
    return;
  }

  const rows = open
    .map((r) => {
      const oddsNum = toNumber(r.odds);
      const implied = r._implied_prob;
      const payout = r._potential_payout;
      const stake = toNumber(r.bet_amount);

      return `
        <tr>
          <td>${r.timestamp || "—"}</td>
          <td>${normalizeSport(r.sport)}</td>
          <td>${r.event}</td>
          <td>${normalizeMarket(r.market)}</td>
          <td>${r.team}</td>
          <td>${r.line ?? "—"}</td>
          <td>${formatAmericanOdds(oddsNum)}</td>
          <td>$${stake.toFixed(2)}</td>
          <td>${formatPct(implied)}</td>
          <td>${
            Number.isFinite(payout)
              ? "$" + payout.toFixed(2)
              : "—"
          }</td>
          <td>${r.status || "open"}</td>
        </tr>
      `;
    })
    .join("");

  section.innerHTML = `
    <div class="section-title">Open Bets (Raw Feed)</div>

    <div class="table-wrapper">
      <table class="history-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Sport</th>
            <th>Event</th>
            <th>Market</th>
            <th>Team</th>
            <th>Line</th>
            <th>Odds</th>
            <th>Stake</th>
            <th>Implied</th>
            <th>Potential Payout</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          ${rows}
        </tbody>
      </table>
    </div>
  `;
}

/* ========= META ========= */

function setLastUpdated(ts) {
  const el = document.getElementById("last-updated");
  if (!el) return;
  const label = ts ? ts : new Date().toLocaleString();
  el.textContent = "Last update: " + label;
}
