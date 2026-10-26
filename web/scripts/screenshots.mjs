// Screenshot every page in dark and light mode and report console errors.
//   node scripts/screenshots.mjs [outDir] [pages...]
// Uses the installed Microsoft Edge (no browser download).
import { chromium } from "playwright"
import fs from "node:fs"
import path from "node:path"

const BASE = process.env.WEB_URL ?? "http://127.0.0.1:3000"
const out = process.argv[2] ?? "../logs/shots"
const pages = process.argv.slice(3).length ? process.argv.slice(3) : ["/", "/map", "/pnl", "/routes", "/history"]
fs.mkdirSync(out, { recursive: true })

const browser = await chromium.launch({ channel: "msedge", headless: true })
const problems = []
for (const theme of ["dark", "light"]) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 })
  await ctx.addInitScript((t) => {
    try {
      localStorage.setItem("theme", t)
    } catch {}
  }, theme)
  for (const p of pages) {
    const page = await ctx.newPage()
    page.on("console", (m) => {
      if (m.type() === "error" || m.type() === "warning") problems.push(`[${theme} ${p}] ${m.type()}: ${m.text().slice(0, 300)}`)
    })
    page.on("pageerror", (e) => problems.push(`[${theme} ${p}] pageerror: ${e.message.slice(0, 300)}`))
    await page.goto(BASE + p, { waitUntil: "domcontentloaded", timeout: 180000 })
    await page.waitForTimeout(Number(process.env.WAIT_MS ?? 6000))
    const name = (p === "/" ? "live" : p.slice(1).replace(/\//g, "_")) + `-${theme}.png`
    await page.screenshot({ path: path.join(out, name), fullPage: true })
    console.log("shot", name)
    await page.close()
  }
  await ctx.close()
}
await browser.close()
console.log(problems.length ? "PROBLEMS:\n" + problems.join("\n") : "no console errors")
