// Screenshot Live Operations for each period, then check that a day row opens Daily P&L.
import { chromium } from "playwright"
const WEB = process.env.WEB_URL ?? "http://localhost:3000"
const out = process.argv[2] ?? "../logs/shots"
const b = await chromium.launch({ channel: "msedge", headless: true })
const errors = []
for (const [period, theme] of [["month", "dark"], ["6m", "dark"], ["year", "dark"], ["ytd", "dark"], ["year", "light"]]) {
  const ctx = await b.newContext({ viewport: { width: 1440, height: 1000 } })
  await ctx.addInitScript(([p, t]) => { localStorage.setItem("airline-twin:period", p); localStorage.setItem("theme", t) }, [period, theme])
  const page = await ctx.newPage()
  page.on("console", (m) => m.type() === "error" && errors.push(`[${period}] ${m.text().slice(0, 200)}`))
  page.on("pageerror", (e) => errors.push(`[${period}] ${e.message.slice(0, 200)}`))
  await page.goto(WEB + "/", { waitUntil: "domcontentloaded" })
  await page.waitForTimeout(7000)
  await page.screenshot({ path: `${out}/live-${period}-${theme}.png`, fullPage: true })
  console.log("shot", period, theme)
  if (period === "month" && theme === "dark") {
    const row = page.locator("tbody tr[title='Open in Daily P&L']").nth(3)
    const label = (await row.locator("td").first().innerText()).trim()
    await row.click()
    await page.waitForURL(/\/pnl\?day=/, { timeout: 30000 })
    await page.waitForTimeout(6000)
    const heading = await page.locator("text=/Why this day lost money|What drove this day/").first().innerText()
    const shown = await page.locator("text=/(Mon|Tue|Wed|Thu|Fri|Sat|Sun) \\d+ \\w{3}/").first().innerText()
    console.log(`row "${label}" -> ${page.url().split("/").pop()} | ${heading} | ${shown}`)
  }
  await ctx.close()
}
await b.close()
console.log(errors.length ? "ERRORS:\n" + errors.join("\n") : "no console errors")
