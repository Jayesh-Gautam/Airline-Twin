// Check that Tailwind generates utilities through the same PostCSS chain as Next.js.
//   NAPI_RS_FORCE_WASI=1 node scripts/tw-check.mjs
import fs from "node:fs"
import path from "node:path"
import postcss from "postcss"
import tailwind from "@tailwindcss/postcss"
import sources from "../tailwind-wasm-sources.cjs"

const from = path.resolve("src/app/globals.css")
const out = await postcss([sources(), tailwind()]).process(fs.readFileSync(from, "utf8"), { from })
const t = out.css
const want = [".flex", "grid-cols-12", "text-loss", "bg-\\(--color-bg\\)", "lg\\:col-span-4", "backdrop-blur"]
console.log("bytes", t.length)
for (const w of want) console.log(" ", w, t.includes(w))
