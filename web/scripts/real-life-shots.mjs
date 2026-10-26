// Screenshot the real-life conditions popover, the Scenario sheet and the feed.
import { chromium } from "playwright"
const WEB = process.env.WEB_URL ?? "http://localhost:3000"
const out = process.argv[2] ?? "../logs/shots"
const b = await chromium.launch({ channel: "msedge", headless: true })
const ctx = await b.newContext({ viewport: { width: 1440, height: 1000 } })
await ctx.addInitScript(() => { localStorage.setItem("airline-twin:period", "day"); localStorage.setItem("theme", "dark") })
const page = await ctx.newPage()
const errors = []
page.on("console", (m) => m.type() === "error" && errors.push(m.text().slice(0, 200)))
page.on("pageerror", (e) => errors.push(e.message.slice(0, 200)))
await page.goto(WEB + "/", { waitUntil: "domcontentloaded" })
await page.waitForTimeout(7000)
await page.getByRole("button", { name: "Real-life conditions" }).click()
await page.waitForTimeout(800)
await page.screenshot({ path: `${out}/real-life-popover.png` })
await page.keyboard.press("Escape")
await page.getByRole("button", { name: /Scenario/ }).click()
await page.waitForTimeout(1500)
await page.screenshot({ path: `${out}/real-life-sheet.png` })
await b.close()
console.log(errors.length ? "ERRORS:\n" + errors.join("\n") : "no console errors")
