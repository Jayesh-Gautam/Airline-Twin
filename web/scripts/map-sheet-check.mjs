// Click a plane on the map and verify the flight panel is drawn above the map.
import { chromium } from "playwright"
const WEB = process.env.WEB_URL ?? "http://localhost:3000"
const b = await chromium.launch({ channel: "msedge", headless: true })
const page = await b.newPage({ viewport: { width: 1440, height: 1000 } })
await page.goto(WEB + "/map", { waitUntil: "domcontentloaded" })
await page.waitForSelector(".plane-icon", { timeout: 60000 })
await page.waitForTimeout(1500)
await page.locator(".plane-icon").first().click({ force: true })
await page.waitForSelector("[data-slot=sheet-content]", { timeout: 10000 })
await page.waitForTimeout(800)
const box = await page.locator("[data-slot=sheet-content]").boundingBox()
const points = [[0.5, 0.3], [0.5, 0.6], [0.2, 0.8], [0.8, 0.5]].map(([fx, fy]) => [box.x + box.width * fx, box.y + box.height * fy])
const onTop = await page.evaluate((pts) => pts.map(([x, y]) => !!document.elementFromPoint(x, y)?.closest("[data-slot=sheet-content]")), points)
await page.screenshot({ path: process.argv[2] ?? "../logs/shots/map-sheet.png" })
await b.close()
console.log(`panel on top at ${onTop.filter(Boolean).length}/${onTop.length} sample points`)
