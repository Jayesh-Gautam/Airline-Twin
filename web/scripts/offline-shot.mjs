// Screenshot the map with the offline world-outline fallback selected.
import { chromium } from "playwright"
const b = await chromium.launch({ channel: "msedge", headless: true })
const p = await b.newPage({ viewport: { width: 1440, height: 1000 } })
const errs = []
p.on("pageerror", (e) => errs.push(e.message))
await p.goto((process.env.WEB_URL ?? "http://localhost:3000") + "/map", { waitUntil: "domcontentloaded" })
await p.waitForSelector(".leaflet-container", { timeout: 60000 })
await p.getByRole("radio", { name: "Offline outline" }).click()
await p.waitForTimeout(4000)
await p.screenshot({ path: process.argv[2] ?? "../logs/shots/map-offline.png" })
await b.close()
console.log(errs.length ? errs.join("\n") : "offline map ok")
