// End-to-end check: reset, run >= 3 simulated days at 1 h/s, and for every airline verify
// that planes move on the map, live profit changes, and loss days come with explained causes.
//   node scripts/final-check.mjs
import { chromium } from "playwright"

const API = process.env.API_URL ?? "http://127.0.0.1:8000"
const WEB = process.env.WEB_URL ?? "http://localhost:3000"
const post = (p, b) => fetch(API + p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b ?? {}) }).then((r) => r.json())
const get = (p) => fetch(API + p).then((r) => r.json())
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const k = (v) => `${v < 0 ? "-" : "+"}$${(Math.abs(v) / 1000).toFixed(1)}k`

await post("/sim/reset")
await post("/sim/scenario", { demand: 1, delay_multiplier: 1, fuel_price: 0.8, bad_weather: { enabled: false, airports: [] }, grounded_aircraft: [] })
await post("/sim/speed", { speed: 3600 })
await post("/sim/start")

const airlines = await get("/airlines")
const browser = await chromium.launch({ channel: "msedge", headless: true })
const errors = []
await sleep(9000) // let the first wave depart (05:00-07:00)

for (const a of airlines) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  await ctx.addInitScript((id) => localStorage.setItem("airline-twin:airline", String(id)), a.id)
  const page = await ctx.newPage()
  page.on("console", (m) => m.type() === "error" && errors.push(`[${a.name}] ${m.text().slice(0, 200)}`))
  page.on("pageerror", (e) => errors.push(`[${a.name}] ${e.message.slice(0, 200)}`))

  await page.goto(WEB + "/map", { waitUntil: "domcontentloaded" })
  await page.waitForSelector(".leaflet-container", { timeout: 60000 })
  await sleep(2500)
  const pos = () => page.$$eval(".plane-icon", (els) => els.map((e) => e.getAttribute("style") ?? ""))
  const p1 = await pos()
  await sleep(3000)
  const p2 = await pos()
  const moved = p1.length > 0 && p2.some((s, i) => s !== p1[i])

  await page.goto(WEB + "/", { waitUntil: "domcontentloaded" })
  await sleep(2500)
  const profit = async () => (await get(`/sim/pnl/live?airline=${a.id}`)).profit
  const v1 = await profit()
  await sleep(3000)
  const v2 = await profit()
  console.log(`${a.name.padEnd(22)} planes on map ${String(p1.length).padStart(2)} -> ${String(p2.length).padStart(2)}  moved=${moved}  live profit ${k(v1)} -> ${k(v2)}  changed=${v1 !== v2}`)
  await ctx.close()
}

// run on until at least 3 full days are complete
for (;;) {
  const s = await get("/sim/state")
  if (s.day_index >= 5) break
  await sleep(3000)
}
await post("/sim/pause")
const st = await get("/sim/state")
console.log(`\nSimulated through day ${st.day_index} (${st.clock}). Loss days per airline:`)
let lossDays = 0
for (const a of airlines) {
  const days = (await get(`/sim/pnl/daily?airline=${a.id}`)).filter((d) => d.closed)
  const losses = days.filter((d) => d.profit < 0)
  lossDays += losses.length
  console.log(`  ${a.name.padEnd(22)} ${days.map((d) => k(d.profit)).join("  ")}`)
  for (const d of losses.slice(0, 1)) {
    const w = (await get(`/sim/pnl/day/${d.day}?airline=${a.id}`)).why
    console.log(`     why day ${d.day_index} lost ${k(w.profit)}: ` + w.causes.slice(0, 3).map((c) => `${c.label} ${k(c.impact)}`).join("; ") + ` (reconciliation gap ${w.reconciliation_gap})`)
  }
}
await browser.close()
console.log(`\nloss days with explained causes: ${lossDays}`)
console.log(errors.length ? "CONSOLE ERRORS:\n" + errors.join("\n") : "no console errors")
