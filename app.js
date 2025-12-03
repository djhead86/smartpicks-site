// smartpicks-site/app.js
// Minimal frontend wired to smart_picks v0.1.7 JSON

const DATA_URL = "data/data.json?ts=${Date.now()}";

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

/* ========= LOAD DATA.JSON ========= */

async function loadData() {
  try {
    const res = await fetch(DATA_URL, { cache: "no-store" });
    const data = await res.json();

    renderSummaryTab(data);
    renderPicksTab(data);
    renderAnalyticsTab(data);
    renderHistoryTab(data);
    setLastUpdated(data.last_updated);
  } catch (err) {
    console.error("Failed to load data.json", err);
    document.getElementById("summary").innerHTML =
      "<p class='muted'>Failed to load SmartPicks data.json.</p>";
  }
}

/* ========= HELPERS ========= */

function normalizeSport(sport) {
  const map = {
    basketball_nba: "NBA",
    americanfootball_nfl: "NFL",
    icehockey_nhl: "NHL",
  };
  return map[sport] || (sport ? sport.toUpperCase() : "Unknown");
}

function normalizeMarket(m) {
  const map = {
    h2h: "Moneyline",
    spreads: "Spread",
    totals: "Over/Under",
  };
  return map[m] || (m ? m.toUpperCase() : "—");
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

function classifyScoreBadge(score) {
  if (!Number.isFinite(score)) return "badge-ev-neutral";
  if (score > 0.05) return "badge-ev-positive";
  if (score < -0.01) return "badge-ev-negative";
  return "badge-ev-neutral";
}

/* ========= SUMMARY TAB ========= */

function renderSummaryTab(data) {
  const section = document.getElementById("summary");

  const stats = data.stats || {};
  const streak = data.streak || {};

  const bankroll = data.bankroll ?? stats.bankroll ?? 0;
  const wins = stats.wins || 0;
  const losses = stats.losses || 0;
  const pushes = stats.pushes || 0;
  const totalBets = stats.lifetime_bets || wins + losses + pushes;

  const winRate = stats.win_rate ?? (totalBets ? wins / totalBets : 0);
  const roi = stats.lifetime_roi ?? 0;
  const currentStreak = streak.current ?? 0;

  const streakLabel =
    currentStreak > 0
      ? `W${currentStreak}`
      : currentStreak < 0
      ? `L${Math.abs(currentStreak)}`
      : "Even";

  section.innerHTML = `
    <div class="section-title">Bankroll & Performance</div>

    <div class="summary-grid">
      <div class="metric-card">
        <div class="metric-label">Bankroll</div>
        <div class="metric-value">$${bankroll.toFixed(2)}</div>
        <div class="metric-sub">Starting from $${(stats.bankroll_start || 200).toFixed(2)}</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">Record</div>
        <div class="metric-value">${wins}-${losses}-${pushes}</div>
        <div class="metric-sub">Total bets: ${totalBets}</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">Win Rate</div>
        <div class="metric-value">${formatPct(winRate)}</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">Lifetime ROI</div>
        <div class="metric-value">${formatPct(roi)}</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">Current Streak</div>
        <div class="metric-value">${streakLabel}</div>
        <div class="metric-sub">
          Best: W${streak.max_win_streak ?? 0} / Worst: L${Math.abs(
    streak.max_loss_streak ?? 0
  )}
        </div>
      </div>

      <div class="metric-card">
        <div class="metric-label">Open Bets</div>
        <div class="metric-value">${(data.open_bets || []).length}</div>
        <div class="metric-sub">${data.new_picks_generated ? "New picks added this run" : "No new picks this run"}</div>
      </div>
    </div>

    <div class="summary-blurb">
      SmartPicksGPT is a small, disciplined engine that grades past bets, updates bankroll,
      and proposes a limited set of value plays based on odds, injuries, and simple risk rules.
      For educational use only.
    </div>
  `;
}

/* ========= PICKS TAB ========= */

function renderPicksTab(data) {
  const section = document.getElementById("picks");
  const picks = data.todays_picks || [];

  // === 72-HOUR TIME FILTER ===
  const now = new Date();
  const MAX_HOURS = 72;

  const filtered = picks.filter(p => {
    const gt = new Date(p.game_time);
    const hoursAhead = (gt - now) / (1000 * 60 * 60);
    return hoursAhead >= 0 && hoursAhead <= MAX_HOURS;
  });

  if (!filtered.length) {
    section.innerHTML = `
      <p class="muted">
        No picks scheduled in the next 72 hours.
      </p>`;
    return;
  }

  // === RENDER PICK CARDS ===
  section.innerHTML = `
    <div class="section-title">Upcoming Picks (Next 72 Hours)</div>
    <div class="picks-grid">
      ${filtered
        .map((p, i) => {
          const match = p.event || p.event_name || "";
          const when = p.game_time || "TBD";
          const prob = Number.isFinite(p.win_probability)
            ? (p.win_probability * 100).toFixed(1) + "%"
            : "—";

          return `
            <article class="pick-card">
              <div class="pick-header">
                <div>
                  <div class="pick-rank">#${i + 1}</div>
                  <div class="pick-main">
                    ${p.team}
                    <span class="pick-match">${match}</span>
                  </div>
                </div>
                <div class="pick-rank">${normalizeMarket(p.market)}</div>
              </div>

              <div class="pick-match">${when}</div>

              <div class="pick-meta-row">
                <span class="badge badge-sport">${normalizeSport(p.sport)}</span>
                <span class="badge badge-price">Odds: ${formatAmericanOdds(
                  p.odds
                )}</span>
                <span class="badge ${classifyScoreBadge(
                  p.score
                )}">Score: ${p.score.toFixed(3)}</span>
                <span class="badge badge-price">Win prob: ${prob}</span>
              </div>

              <p class="pick-reason">
                Simple value signal based on probability edges and conservative risk rules.
              </p>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}


/* ========= ANALYTICS TAB ========= */

function renderAnalyticsTab(data) {
  const section = document.getElementById("analytics");
  const stats = data.stats || {};
  const breakdown = stats.sport_breakdown || {};

  const rows = Object.entries(breakdown).map(([sport, s]) => {
    const roi = Number.isFinite(s.roi) ? (s.roi * 100).toFixed(1) + "%" : "—";
    const stake = Number.isFinite(s.stake) ? `$${s.stake.toFixed(2)}` : "—";
    const pnl = Number.isFinite(s.pnl) ? formatMoney(s.pnl) : "—";

    return `
      <tr>
        <td>${normalizeSport(sport)}</td>
        <td>${s.wins}</td>
        <td>${s.losses}</td>
        <td>${s.pushes}</td>
        <td>${stake}</td>
        <td>${pnl}</td>
        <td>${roi}</td>
      </tr>
    `;
  });

  section.innerHTML = `
    <div class="section-title">Sport Breakdown</div>

    <div class="analytics-card">
      <div class="table-wrapper">
        <table class="history-table">
          <thead>
            <tr>
              <th>Sport</th>
              <th>W</th>
              <th>L</th>
              <th>P</th>
              <th>Staked</th>
              <th>PnL</th>
              <th>ROI</th>
            </tr>
          </thead>
          <tbody>
            ${
              rows.length
                ? rows.join("")
                : `<tr><td colspan="7" class="muted">No graded bets yet.</td></tr>`
            }
          </tbody>
        </table>
      </div>
    </div>
  `;
}

/* ========= HISTORY TAB ========= */

function renderHistoryTab(data) {
  const section = document.getElementById("history");
  const open = data.open_bets || [];

  if (!open.length) {
    section.innerHTML = `
      <div class="section-title">Open Bets</div>
      <p class="muted">No open bets right now. Once smart_picks.py places new wagers,
      they will appear here until graded.</p>
    `;
    return;
  }

  section.innerHTML = `
    <div class="section-title">Open Bets</div>

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
          </tr>
        </thead>
        <tbody>
          ${open
            .map((r) => {
              return `
              <tr>
                <td>${r.timestamp || "—"}</td>
                <td>${normalizeSport(r.sport)}</td>
                <td>${r.event}</td>
                <td>${normalizeMarket(r.market)}</td>
                <td>${r.team}</td>
                <td>${r.line ?? 0}</td>
                <td>${formatAmericanOdds(Number(r.odds))}</td>
                <td>$${Number(r.bet_amount || 0).toFixed(2)}</td>
              </tr>
            `;
            })
            .join("")}
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
