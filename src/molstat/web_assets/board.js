"use strict";

const POLL_INTERVAL_MS = 30000;
const PAGE_INTERVAL_MS = 20000;
const CARDS_PER_PAGE = 12;
const params = new URLSearchParams(window.location.search);
const tvMode = params.get("mode") === "tv";
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

let lastSnapshot = null;
let currentPage = 0;
let pageTimer = null;

const byId = (id) => document.getElementById(id);

function formatAge(hours) {
  if (hours === null || hours === undefined) return "—";
  if (hours < 1) return `${Math.round(hours * 60)} min`;
  if (hours < 24) return `${hours.toFixed(1)} t`;
  return `${(hours / 24).toFixed(1)} d`;
}

function setText(id, value) {
  byId(id).textContent = String(value);
}

function makeMetric(label, value) {
  const wrapper = document.createElement("div");
  const term = document.createElement("dt");
  const data = document.createElement("dd");
  term.textContent = label;
  data.textContent = String(value);
  wrapper.append(term, data);
  return wrapper;
}

function makeAge(label, value) {
  const wrapper = document.createElement("div");
  const text = document.createElement("span");
  const number = document.createElement("strong");
  text.className = "age-label";
  number.className = "age-value";
  text.textContent = label;
  number.textContent = formatAge(value);
  wrapper.append(text, number);
  return wrapper;
}

function severityText(severity) {
  if (severity === "OVERDUE") return "Over frist";
  if (severity === "WARNING") return "Varsel";
  return "Normal";
}

function createCard(analysis) {
  const card = document.createElement("article");
  card.className = `analysis-card ${analysis.severity.toLowerCase()}`;
  card.setAttribute("aria-label", `${analysis.label}: ${severityText(analysis.severity)}`);

  const header = document.createElement("div");
  header.className = "card-header";
  const title = document.createElement("h3");
  title.textContent = analysis.label;
  const status = document.createElement("span");
  status.className = "status-tag";
  status.textContent = severityText(analysis.severity);
  header.append(title, status);

  const counts = document.createElement("dl");
  counts.className = "card-counts";
  counts.append(
    makeMetric("Klare", analysis.ready),
    makeMetric("Ikke godkj.", analysis.awaitingApproval),
    makeMetric("På vei", analysis.inTransit)
  );

  const ages = document.createElement("div");
  ages.className = "age-row";
  ages.append(
    makeAge("Median klar", analysis.medianReadyHours),
    makeAge("Eldste klar", analysis.oldestReadyHours)
  );

  card.append(header, counts, ages);
  return card;
}

function pageCount(snapshot) {
  return tvMode ? Math.max(1, Math.ceil(snapshot.analyses.length / CARDS_PER_PAGE)) : 1;
}

function analysesForPage(snapshot) {
  if (!tvMode) return snapshot.analyses;
  const start = currentPage * CARDS_PER_PAGE;
  return snapshot.analyses.slice(start, start + CARDS_PER_PAGE);
}

function render(snapshot) {
  lastSnapshot = snapshot;
  const pages = pageCount(snapshot);
  if (currentPage >= pages) currentPage = 0;

  setText("unit-label", snapshot.unitLabel);
  const generated = new Date(snapshot.generatedAt);
  setText("generated-at", `Oppdatert ${generated.toLocaleString("nb-NO")}`);
  setText("ready-total", snapshot.totals.ready);
  setText("approval-total", snapshot.totals.awaitingApproval);
  setText("transit-total", snapshot.totals.inTransit);
  setText("overdue-total", snapshot.totals.overdue);
  setText("empty-count", `${snapshot.emptyAnalysisCount} områder uten prøver`);
  setText("page-indicator", `Side ${currentPage + 1} av ${pages}`);
  byId("stale-banner").hidden = !snapshot.isStale;

  const grid = byId("analysis-grid");
  grid.replaceChildren();
  analysesForPage(snapshot).forEach((analysis) => grid.append(createCard(analysis)));
  byId("empty-state").hidden = snapshot.analyses.length !== 0;
  schedulePageRotation(pages);
}

function schedulePageRotation(pages) {
  if (pageTimer !== null) window.clearInterval(pageTimer);
  pageTimer = null;
  if (!tvMode || pages <= 1) return;
  pageTimer = window.setInterval(() => {
    currentPage = (currentPage + 1) % pages;
    if (lastSnapshot) render(lastSnapshot);
  }, PAGE_INTERVAL_MS);
}

async function fetchSnapshot() {
  try {
    const response = await fetch("/api/v1/snapshot", {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" }
    });
    if (!response.ok) throw new Error("snapshot unavailable");
    const snapshot = await response.json();
    byId("offline-status").hidden = true;
    render(snapshot);
  } catch (_error) {
    byId("offline-status").hidden = false;
    if (lastSnapshot) render(lastSnapshot);
  }
}

if (reducedMotion) document.documentElement.classList.add("reduced-motion");
fetchSnapshot();
window.setInterval(fetchSnapshot, POLL_INTERVAL_MS);

