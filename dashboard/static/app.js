/* Airline digital twin dashboard. Data comes from the Flask API (MongoDB). */
const $ = id => document.getElementById(id);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const n0 = v => Number(v).toLocaleString("en-US", { maximumFractionDigits: 0 });
const n2 = v => Number(v).toLocaleString("en-US", { maximumFractionDigits: 2 });
const pct = v => (v * 100).toFixed(1) + "%";
const money = v => {
  const a = Math.abs(v);
  return a >= 1e9 ? (v / 1e9).toFixed(2) + "B" : a >= 1e6 ? (v / 1e6).toFixed(2) + "M" : a >= 1e3 ? (v / 1e3).toFixed(1) + "K" : n0(v);
};
const axMoney = v => { const a = Math.abs(v); return a >= 1e6 ? +(v / 1e6).toFixed(1) + "M" : a >= 1e3 ? +(v / 1e3).toFixed(0) + "K" : n0(v); };
const sign = v => (v >= 0 ? "pos" : "neg");
const api = async p => { const r = await fetch(p); if (!r.ok) throw new Error(p + " " + r.status); return r.json(); };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad = v => String(v).padStart(2, "0");

/* ---------- charts ---------- */
const charts = {};
function chart(id, cfg) {
  if (charts[id]) charts[id].destroy();
  Chart.defaults.color = css("--ink2");
  Chart.defaults.borderColor = css("--grid");
  Chart.defaults.font.family = "system-ui, -apple-system, 'Segoe UI', sans-serif";
  cfg.options = Object.assign({ responsive: true, maintainAspectRatio: false, animation: { duration: 250 } }, cfg.options || {});
  return (charts[id] = new Chart($(id), cfg));
}
/* show the year once, on the first label of each year (labels are ISO dates / year-months) */
const yearTicks = suffix => ({ autoSkip: false, maxRotation: 0, callback(v) { const l = this.getLabelForValue(v); return l.endsWith(suffix) ? l.slice(0, 4) : ""; } });
function bars(id, labels, datasets, { horizontal = false, fmt = n0, legend = false, stacked = false } = {}) {
  return chart(id, {
    type: "bar",
    data: { labels, datasets: datasets.map(d => Object.assign({ borderRadius: 4, maxBarThickness: 26 }, d)) },
    options: {
      indexAxis: horizontal ? "y" : "x",
      plugins: { legend: { display: legend }, tooltip: { callbacks: { label: c => `${c.dataset.label ? c.dataset.label + ": " : ""}${fmt(c.parsed[horizontal ? "x" : "y"])}` } } },
      scales: { x: { grid: { display: !horizontal }, ticks: horizontal ? { callback: v => fmt(v) } : {}, stacked },
                y: { grid: { display: !horizontal }, ticks: horizontal ? {} : { callback: v => fmt(v) }, stacked } },
    },
  });
}
function table(el, rows, cols) {
  cols = cols || Object.keys(rows[0] || {});
  const isNum = v => typeof v === "number";
  el.innerHTML = "<thead><tr>" + cols.map(c => `<th class="${rows.length && isNum(rows[0][c]) ? "num" : ""}">${c.replace(/_/g, " ")}</th>`).join("") +
    "</tr></thead><tbody>" + rows.map(r => "<tr>" + cols.map(c => {
      const v = r[c];
      const txt = isNum(v) ? (c === "id" ? String(v) : Number.isInteger(v) ? n0(v) : n2(v)) : (v ?? "");
      return `<td class="${isNum(v) ? "num" : ""}">${txt}</td>`;
    }).join("") + "</tr>").join("") + "</tbody>";
}

/* ---------- tabs ---------- */
const loaders = {}, loaded = {};
$("tabs").addEventListener("click", e => {
  const t = e.target.dataset.tab; if (!t) return;
  document.querySelectorAll("nav button").forEach(b => b.classList.toggle("active", b === e.target));
  document.querySelectorAll(".tab").forEach(s => s.classList.toggle("active", s.id === "tab-" + t));
  if (t !== "sim") pause();
  if (loaders[t] && !loaded[t]) { loaded[t] = true; loaders[t]().catch(err => console.error(err)); }
  else Object.values(charts).forEach(c => c.resize());
});

/* ======================= SIMULATION ======================= */
const DAY = 86400000;
const S = { series: [], start: 0, simMs: 0, playing: false, last: 0, cache: new Map(), pending: new Set(),
            cur: null, drawnDate: null, lastPaint: 0, idx: 0 };

const markerPlugin = {
  id: "marker",
  afterDraw(c) {
    if (c.canvas.id !== "cCum" || !S.series.length) return;
    const x = c.scales.x.getPixelForValue(S.idx), { top, bottom } = c.chartArea, g = c.ctx;
    g.save(); g.strokeStyle = css("--s2"); g.lineWidth = 2; g.beginPath(); g.moveTo(x, top); g.lineTo(x, bottom); g.stroke();
    g.fillStyle = css("--s2"); g.beginPath(); g.arc(x, c.scales.y.getPixelForValue(S.series[S.idx].cumulative_revenue), 5, 0, 7); g.fill(); g.restore();
  },
};
Chart.register(markerPlugin);

async function loadDay(date) {
  if (S.cache.has(date)) return S.cache.get(date);
  if (S.pending.has(date)) return null;
  S.pending.add(date);
  try { const d = await api("/api/sim/day?date=" + date); S.cache.set(date, d); if (S.cache.size > 60) S.cache.delete(S.cache.keys().next().value); return d; }
  finally { S.pending.delete(date); }
}

async function initSim() {
  S.series = await api("/api/sim/series");
  S.start = Date.parse(S.series[0].date + "T00:00:00Z");
  S.simMs = S.start;
  const h = location.hash.match(/^#(\d{4}-\d{2}-\d{2})(?:T(\d\d):(\d\d))?/);   // e.g. #2024-05-11T08:30
  if (h) { const t = Date.parse(`${h[1]}T${h[2] || "00"}:${h[3] || "00"}:00Z`); if (!isNaN(t)) S.simMs = Math.max(S.start, Math.min(t, S.start + S.series.length * DAY - 1)); }
  $("slider").max = S.series.length - 1;
  $("datePick").min = S.series[0].date; $("datePick").max = S.series[S.series.length - 1].date;
  chart("cCum", { type: "line",
    data: { labels: S.series.map(d => d.date), datasets: [{ label: "Cumulative fare revenue", data: S.series.map(d => d.cumulative_revenue), borderColor: css("--s1"), borderWidth: 2, pointRadius: 0, fill: false }] },
    options: { plugins: { legend: { display: false } }, scales: { x: { ticks: yearTicks("-01-01"), grid: { display: false } }, y: { ticks: { callback: axMoney } } } } });
  chart("cDaily", { type: "bar",
    data: { labels: [], datasets: [
      { label: "Daily revenue", data: [], backgroundColor: css("--s1"), borderRadius: 3, order: 2 },
      { type: "line", label: "7-day average", data: [], borderColor: css("--s2"), borderWidth: 2, pointRadius: 0, order: 1 }] },
    options: { plugins: { legend: { display: true } }, scales: { x: { ticks: { maxTicksLimit: 6 }, grid: { display: false } }, y: { ticks: { callback: axMoney } } } } });
  chart("cAirlines", { type: "bar", data: { labels: [], datasets: [{ data: [], backgroundColor: css("--s1"), borderRadius: 4 }] },
    options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { ticks: { callback: axMoney } }, y: { grid: { display: false } } } } });
  requestAnimationFrame(loop);
  paint(true);
}

function loop(t) {
  const dt = Math.min(0.25, (t - S.last) / 1000); S.last = t;
  if (S.playing) {
    S.simMs += dt * Number($("speed").value) * 1000;
    const end = S.start + S.series.length * DAY - 1;
    if (S.simMs >= end) { S.simMs = end; pause(); }
  }
  if (t - S.lastPaint > 90) { S.lastPaint = t; paint(false); }
  requestAnimationFrame(loop);
}

function paint(force) {
  S.idx = Math.max(0, Math.min(S.series.length - 1, Math.floor((S.simMs - S.start) / DAY)));
  const day = S.series[S.idx], dayStart = S.start + S.idx * DAY, now = S.simMs;
  const d = new Date(now);
  $("clkDow").textContent = day.day_of_week;
  $("clkDate").textContent = `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  $("clkTime").textContent = `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
  if (!$("slider").matches(":active")) $("slider").value = S.idx;
  if (document.activeElement !== $("datePick")) $("datePick").value = day.date;

  const data = S.cache.get(day.date);
  if (!data) { loadDay(day.date).then(r => r && paint(true)); }
  else S.cur = data;
  if (!S.cur) return;

  const fl = (S.cur.date === day.date) ? S.cur.flights : [];
  const dep = f => Date.parse(f.departure_time), arr = f => Date.parse(f.arrival_time);
  const today = fl.filter(f => dep(f) >= dayStart);
  const departed = today.filter(f => dep(f) <= now);
  const airborne = fl.filter(f => dep(f) <= now && now < arr(f));
  const before = S.idx > 0 ? S.series[S.idx - 1] : { cumulative_revenue: 0, cumulative_profit_est: 0 };
  $("kAir").textContent = airborne.length;
  $("kDep").textContent = `${departed.length} / ${today.length}`;
  $("kPax").textContent = n0(departed.reduce((s, f) => s + f.passengers, 0));
  $("kDel").textContent = departed.filter(f => f.is_delayed).length;
  $("kRev").textContent = money(before.cumulative_revenue + departed.reduce((s, f) => s + f.fare_revenue, 0));
  const prof = before.cumulative_profit_est + departed.reduce((s, f) => s + f.operating_profit_est, 0);
  $("kProf").textContent = money(prof); $("kProf").className = sign(prof);

  const rows = fl.filter(f => dep(f) >= dayStart || now < arr(f));
  $("boardNote").textContent = today.length ? `${today.length} departures today` : "no departures today";
  $("board").tBodies[0].innerHTML = rows.length ? rows.map(f => {
    const air = dep(f) <= now && now < arr(f), done = now >= arr(f), prog = air ? (now - dep(f)) / (arr(f) - dep(f)) : done ? 1 : 0;
    const st = air ? `<span class="badge b-air">In air</span>` : done ? `<span class="badge b-land">Landed</span>` : `<span class="badge b-sched">Scheduled</span>`;
    const dl = f.is_delayed ? `<span class="badge b-delay" title="${f.delay_reason}">+${f.delay_minutes} min</span>` : "";
    const hm = s => s.slice(11, 16);
    return `<tr class="${air ? "flying" : ""}"><td title="${f.airline}">${f.airline.split(" ")[0]} ${f.flight_number}</td><td>${f.origin} &rarr; ${f.destination}</td><td>${f.model_number}</td>` +
      `<td>${hm(f.departure_time)}</td><td>${hm(f.arrival_time)}${arr(f) - dayStart >= DAY ? " +1" : ""}</td><td>${st}${dl}<div class="bar"><i style="width:${(prog * 100).toFixed(0)}%"></i></div></td>` +
      `<td>${f.passengers} / ${f.capacity}${f.passengers > f.capacity ? " &#9888;" : ""}</td></tr>`;
  }).join("") : `<tr><td colspan="7" class="muted">No flights scheduled on this day.</td></tr>`;

  if (force || S.drawnDate !== day.date) {
    S.drawnDate = day.date;
    const a = charts.cAirlines; a.data.labels = S.cur.airlines.map(x => x.airline); a.data.datasets[0].data = S.cur.airlines.map(x => x.revenue); a.update("none");
    const lo = Math.max(0, S.idx - 29), win = S.series.slice(lo, S.idx + 1), c = charts.cDaily;
    c.data.labels = win.map(x => x.date.slice(5)); c.data.datasets[0].data = win.map(x => x.revenue); c.data.datasets[1].data = win.map(x => x.revenue_7d_avg); c.update("none");
    charts.cCum.draw();
    const byOrigin = {}; today.forEach(f => byOrigin[f.origin] = (byOrigin[f.origin] || 0) + 1);
    const top = Object.entries(byOrigin).sort((x, y) => y[1] - x[1]).slice(0, 8);
    $("airportList").innerHTML = top.length ? top.map(([k, v]) => `<span class="chip">${k} <b>${v}</b></span>`).join("") : `<span class="muted">none</span>`;
  }
}

function play() { S.playing = true; S.last = performance.now(); $("play").innerHTML = "&#10074;&#10074; Pause"; }
function pause() { S.playing = false; $("play").innerHTML = "&#9654; Play"; }
$("play").onclick = () => (S.playing ? pause() : play());
$("reset").onclick = () => { pause(); S.simMs = S.start; paint(true); };
$("slider").oninput = e => { S.simMs = S.start + Number(e.target.value) * DAY; paint(true); };
$("datePick").onchange = e => { const t = Date.parse(e.target.value + "T00:00:00Z"); if (!isNaN(t)) { S.simMs = Math.max(S.start, Math.min(t, S.start + (S.series.length - 1) * DAY)); paint(true); } };

/* ======================= OVERVIEW ======================= */
loaders.overview = async () => {
  const o = await api("/api/overview"), k = o.kpi;
  const cards = [["Departures", n0(k.departures)], ["Routes", n0(k.routes)], ["Passenger segments", n0(k.passenger_segments)],
    ["Fare revenue (real)", money(k.fare_revenue)], ["Operating profit (est.)", money(k.operating_profit_est)],
    ["Delay rate (15+ min)", pct(k.delay_rate)], ["Avg load factor", pct(k.avg_load_factor)], ["Fuel burned (est.)", n0(k.fuel_tonnes_est) + " t"]];
  $("ovKpis").innerHTML = cards.map(([a, b]) => `<div class="kpi"><span>${a}</span><b>${b}</b></div>`).join("");
  chart("cMonthly", { type: "line", data: { labels: o.monthly.map(m => m.year_month), datasets: [
      { label: "Fare revenue (real)", data: o.monthly.map(m => m.fare_revenue), borderColor: css("--s1"), borderWidth: 2, pointRadius: 0 },
      { label: "Operating profit (estimate)", data: o.monthly.map(m => m.operating_profit_est), borderColor: css("--s2"), borderWidth: 2, pointRadius: 0 }] },
    options: { plugins: { legend: { display: true } }, scales: { x: { ticks: yearTicks("-01"), grid: { display: false } }, y: { ticks: { callback: axMoney } } } } });
  table($("ovAirlines"), o.airlines.map(a => ({ airline: a.airline, departures: a.departures, fare_revenue: a.fare_revenue, maintenance_cost_est: a.maintenance_cost_est,
    operating_profit_est: a.operating_profit_est, margin_est: Number((a.margin_est * 100).toFixed(1)) })));
  const t = o.timings, total = ["ingest_and_clean", "enrich", "analytics", "mongodb_store"].reduce((s, k2) => s + (t[k2] || 0), 0);
  $("runInfo").textContent = `Spark ${o.spark_version} · ${total.toFixed(0)} s end to end`;
  bars("cTimings", ["Ingest + clean", "Enrich", "Analytics", "MongoDB load"], [{ data: [t.ingest_and_clean, t.enrich, t.analytics, t.mongodb_store], backgroundColor: css("--s1") }], { horizontal: true, fmt: v => v + " s" });
  $("ovCounts").innerHTML = Object.entries(o.counts).map(([k2, v]) => `<span class="chip">${k2} <b>${n0(v)}</b></span>`).join("");
};

/* ======================= ROUTES ======================= */
async function loadRoutes() {
  const a = $("routeAirline").value, r = await api("/api/routes" + (a ? "?airline=" + encodeURIComponent(a) : ""));
  if ($("routeAirline").options.length === 1) r.airlines.forEach(x => $("routeAirline").add(new Option(x, x)));
  $("routeCount").textContent = `${r.count} routes`;
  const lab = x => `${x.route}${a ? "" : " (" + x.airline.split(" ")[0] + ")"}`;
  bars("cTop", r.top.map(lab), [{ data: r.top.map(x => x.profit_est), backgroundColor: css("--s1") }], { horizontal: true, fmt: money });
  bars("cBottom", r.bottom.map(lab), [{ data: r.bottom.map(x => x.profit_est), backgroundColor: css("--s2") }], { horizontal: true, fmt: money });
  table($("routeTable"), r.top.concat(r.bottom).map(x => ({ airline: x.airline, route: x.route, departures: x.departures, avg_load_factor: x.avg_load_factor, revenue: x.revenue,
    profit_est: x.profit_est, margin_pct_est: Number((x.margin_est * 100).toFixed(1)) })));
}
loaders.routes = async () => { $("routeAirline").onchange = loadRoutes; await loadRoutes(); };

/* ======================= DELAYS ======================= */
loaders.delays = async () => {
  const d = await api("/api/delays");
  bars("cReason", d.by_reason.map(x => x.delay_reason), [{ data: d.by_reason.map(x => x.delays), backgroundColor: css("--s1") }], { horizontal: true });
  bars("cAirportDelay", d.by_airport.map(x => `${x.airport} (${x.departures} dep)`), [{ data: d.by_airport.map(x => x.delay_rate), backgroundColor: css("--s1") }], { horizontal: true, fmt: pct });
  bars("cModelDelay", d.by_model.map(x => x.model_number), [{ data: d.by_model.map(x => x.delay_rate), backgroundColor: css("--s1") }], { fmt: pct });
};

/* ======================= FLEET ======================= */
loaders.fleet = async () => {
  const f = await api("/api/fleet");
  bars("cFuel", f.fuel.map(x => `${x.model_number} (${x.capacity})`), [{ data: f.fuel.map(x => x.kg_per_seat_hour_est), backgroundColor: css("--s1") }], { horizontal: true, fmt: v => n2(v) + " kg" });
  const col = { First: "--s1", Business: "--s2", "Premium Economy": "--s3", Economy: "--s4" };
  bars("cCabin", f.cabins.map(x => x.cabin), [{ data: f.cabins.map(x => x.revenue_share), backgroundColor: f.cabins.map(x => css(col[x.cabin])) }], { horizontal: true, fmt: pct });
  bars("cLead", f.lead_time.map(x => x.lead_time.slice(3)), [{ data: f.lead_time.map(x => x.bookings), backgroundColor: css("--s1") }]);
  bars("cAirports", f.airports.map(x => x.airport), [{ label: "Departures", data: f.airports.map(x => x.departures), backgroundColor: css("--s1") },
    { label: "Arrivals", data: f.airports.map(x => x.arrivals), backgroundColor: css("--s2") }], { legend: true, stacked: true });
  table($("utilTable"), f.utilization.map(x => ({ registration: x.registration_number, model: x.model_number, airline: x.airline, departures: x.departures, block_hours: x.block_hours,
    maintenance_events_est: x.maintenance_events, downtime_hours_est: x.maintenance_downtime_hours })));
};

/* ======================= QUALITY ======================= */
loaders.quality = async () => {
  const q = await api("/api/quality"), c = q.clean && q.clean.summary || {}, d = q.dirty && q.dirty.summary || {};
  const keys = Object.keys(Object.assign({}, c, d)).filter(k => k !== "run");
  table($("qSummary"), keys.map(k => ({ metric: k.replace(/_/g, " "), [`clean (${c.run || "-"})`]: c[k] ?? "-", [`dirty (${d.run || "-"})`]: d[k] ?? "-" })));
  const k = q.answer_key, num = v => (isNaN(Number(v)) ? null : Number(v));
  if (k.length) {
    bars("cFaults", k.map(x => x.fault_type), [
      { label: "Present in our 18 tables", data: k.map(x => num(x.in_scope_baseline_18_tables)), backgroundColor: css("--s2") },
      { label: "Detected / fixed by pipeline", data: k.map(x => num(x.detected_or_fixed_by_pipeline)), backgroundColor: css("--s1") }], { horizontal: true, legend: true });
    table($("qKey"), k.map(x => ({ fault: x.fault_type, planted_all_32_tables: num(x.planted_all_32_tables), in_our_18_tables: num(x.in_scope_baseline_18_tables) ?? "n/a", pipeline: num(x.detected_or_fixed_by_pipeline) })));
  }
};

/* ======================= MONGODB ======================= */
loaders.mongo = async () => {
  const e = await api("/api/explorer"), i = e.index;
  $("idxBox").innerHTML = `<span class="chip">query <b>${JSON.stringify(i.query)}</b></span><span class="chip">plan <b>${i.stage}</b> on <b>${i.index}</b></span>` +
    `<span class="chip">documents examined <b>${n0(i.docs_examined)}</b> of ${n0(i.collection_size)}</span>`;
  $("queries").innerHTML = e.queries.map((q, n) => `<div class="card"><h2>${q.title} <small>db.${q.collection}.aggregate &middot; ${q.ms} ms</small></h2>` +
    `<details><summary>Show the aggregation pipeline</summary><pre>${q.pipeline.replace(/</g, "&lt;")}</pre></details><div class="scroll"><table id="q${n}"></table></div></div>`).join("");
  e.queries.forEach((q, n) => table($("q" + n), q.result.map(r => { const o = {}; for (const [a, b] of Object.entries(r)) o[a] = (b && typeof b === "object") ? JSON.stringify(b) : b; return o; })));
};

const tabHash = location.hash.match(/^#tab=(\w+)/);   // e.g. #tab=routes
if (tabHash) document.querySelector(`nav button[data-tab="${tabHash[1]}"]`)?.click();
initSim().catch(err => { document.body.insertAdjacentHTML("afterbegin", `<p style="padding:16px;color:#d03b3b">Could not load data: ${err.message}. Is MongoDB running and the pipeline run?</p>`); });
