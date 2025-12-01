/* style.css - SmartPicksGPT Cyber Dashboard */

:root {
  --bg: #02030a;
  --bg-alt: #050719;
  --bg-elevated: #080b23;
  --border-subtle: rgba(255, 255, 255, 0.08);
  --accent: #4df0ff;
  --accent-soft: rgba(77, 240, 255, 0.18);
  --accent-2: #ff3b9d;
  --accent-3: #a86bff;
  --text: #f5f7ff;
  --text-muted: #9ca4c7;
  --danger: #ff4b6b;
  --success: #5dffb5;
  --pending: #ffd166;
  --radius-lg: 18px;
  --radius-md: 12px;
  --radius-pill: 999px;
  --shadow-soft: 0 20px 60px rgba(0, 0, 0, 0.65);
  --grid-gap: 18px;
  --transition-fast: 160ms ease-out;
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

html,
body {
  margin: 0;
  padding: 0;
  height: 100%;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
}

.sp-body {
  min-height: 100vh;
  background: radial-gradient(circle at top, #111537 0, #040511 45%, #010109 100%);
  color: var(--text);
  position: relative;
  overflow-x: hidden;
}

/* Noise / scanline overlay */

.sp-noise {
  pointer-events: none;
  position: fixed;
  inset: 0;
  opacity: 0.16;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 1600 900' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='4' stitchTiles='noStitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.5'/%3E%3C/svg%3E");
  mix-blend-mode: screen;
}

/* Top bar */

.sp-top-bar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 28px;
  backdrop-filter: blur(18px);
  background: linear-gradient(
    to right,
    rgba(0, 0, 0, 0.85),
    rgba(4, 10, 30, 0.9),
    rgba(0, 0, 0, 0.85)
  );
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.sp-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sp-logo-dot {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: radial-gradient(circle at 30% 30%, #ffffff, var(--accent));
  box-shadow: 0 0 20px var(--accent);
}

.sp-brand-text {
  display: flex;
  flex-direction: column;
}

.sp-title {
  font-size: 1.1rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.sp-subtitle {
  font-size: 0.78rem;
  color: var(--text-muted);
}

.sp-top-meta {
  display: flex;
  gap: 20px;
  align-items: center;
  font-size: 0.8rem;
}

.sp-meta-item {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.sp-label {
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 0.7rem;
  color: var(--text-muted);
}

.sp-value {
  font-variant-numeric: tabular-nums;
}

/* Layout */

.sp-main {
  max-width: 1200px;
  margin: 22px auto 40px;
  padding: 0 18px 40px;
}

.sp-grid {
  display: grid;
  gap: var(--grid-gap);
}

.sp-grid-3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.sp-grid-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

@media (max-width: 960px) {
  .sp-grid-3,
  .sp-grid-2 {
    grid-template-columns: minmax(0, 1fr);
  }

  .sp-top-bar {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .sp-top-meta {
    width: 100%;
    justify-content: space-between;
  }

  .sp-main {
    margin-top: 16px;
  }
}

/* Cards */

.sp-card {
  position: relative;
  border-radius: var(--radius-lg);
  padding: 16px 18px 14px;
  background: radial-gradient(circle at top left, #151a3a 0, #050618 40%, #02020a 100%);
  box-shadow: var(--shadow-soft);
  border: 1px solid rgba(255, 255, 255, 0.06);
  overflow: hidden;
}

.sp-card::before {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.3;
  background: linear-gradient(
    135deg,
    rgba(77, 240, 255, 0.12),
    transparent 35%,
    transparent 65%,
    rgba(168, 107, 255, 0.18)
  );
  mix-blend-mode: screen;
}

.sp-card-header {
  position: relative;
  z-index: 1;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.sp-card-header span:first-child {
  font-size: 0.95rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.sp-card-subtitle {
  font-size: 0.78rem;
  color: var(--text-muted);
}

.sp-card-body {
  position: relative;
  z-index: 1;
}

/* Pills */

.sp-pill {
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  border: 1px solid var(--accent);
  background: rgba(0, 0, 0, 0.6);
  color: var(--accent);
}

.sp-pill-secondary {
  border-color: var(--accent-2);
  color: var(--accent-2);
}

.sp-pill-tertiary {
  border-color: var(--accent-3);
  color: var(--accent-3);
}

/* KPI cards */

.sp-card-kpi {
  padding-bottom: 16px;
}

.sp-kpi-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 16px;
  margin-top: 8px;
}

.sp-kpi {
  display: flex;
  flex-direction: column;
}

.sp-kpi-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.12em;
}

.sp-kpi-value {
  font-variant-numeric: tabular-nums;
  font-size: 1.05rem;
  margin-top: 4px;
}

.sp-kpi-pl {
  color: var(--success);
}

/* Tables */

.sp-table-wrapper {
  max-height: 320px;
  overflow: auto;
  border-radius: var(--radius-md);
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(1, 2, 10, 0.7);
}

.sp-table-history {
  max-height: 360px;
}

.sp-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.78rem;
}

.sp-table thead {
  position: sticky;
  top: 0;
  background: linear-gradient(to right, #090c27, #050618);
  z-index: 1;
}

.sp-table th,
.sp-table td {
  padding: 7px 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  white-space: nowrap;
  text-align: left;
}

.sp-table th {
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  font-size: 0.7rem;
  color: var(--text-muted);
}

.sp-table tbody tr:nth-child(even) {
  background: rgba(255, 255, 255, 0.01);
}

.sp-table tbody tr:hover {
  background: rgba(77, 240, 255, 0.05);
}

.sp-table-sm th,
.sp-table-sm td {
  padding: 6px 8px;
}

/* Chips & States */

.sp-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  font-size: 0.65rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.sp-chip-win {
  background: rgba(93, 255, 181, 0.12);
  border: 1px solid rgba(93, 255, 181, 0.7);
  color: var(--success);
}

.sp-chip-loss {
  background: rgba(255, 75, 107, 0.12);
  border: 1px solid rgba(255, 75, 107, 0.7);
  color: var(--danger);
}

.sp-chip-push {
  background: rgba(255, 209, 102, 0.12);
  border: 1px solid rgba(255, 209, 102, 0.7);
  color: var(--pending);
}

.sp-chip-pending {
  background: rgba(156, 164, 199, 0.12);
  border: 1px solid rgba(156, 164, 199, 0.7);
  color: var(--text-muted);
}

/* Text coloring */

.sp-text-pos {
  color: var(--success);
}

.sp-text-neg {
  color: var(--danger);
}

.sp-empty-row {
  text-align: center;
  color: var(--text-muted);
}

/* Spacing helpers */

.sp-mt-lg {
  margin-top: 22px;
}

/* Footer */

.sp-footer {
  max-width: 1200px;
  margin: 0 auto 20px;
  padding: 0 18px;
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 0.75rem;
  color: var(--text-muted);
  opacity: 0.8;
}

.sp-footer-hint {
  font-style: italic;
}

/* Scrollbars */

.sp-table-wrapper::-webkit-scrollbar {
  height: 6px;
  width: 6px;
}

.sp-table-wrapper::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.4);
}

.sp-table-wrapper::-webkit-scrollbar-thumb {
  background: var(--accent-soft);
  border-radius: var(--radius-pill);
}

