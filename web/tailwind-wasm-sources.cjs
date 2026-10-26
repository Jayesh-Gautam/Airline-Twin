// PostCSS plugin: feed Tailwind v4 its class candidates without the native scanner.
//
// This machine's Application Control policy blocks native .node binaries, so
// Tailwind runs its WebAssembly engine - whose file scanner cannot read Windows
// paths (it finds 0 candidates). Instead we collect every token that appears in a
// string literal under src/ and hand them to Tailwind via `@source inline(...)`,
// which the JavaScript compiler handles. Unknown tokens are simply ignored.
// The src/ directory is registered as a dependency so webpack recompiles the CSS
// when a component changes.
const fs = require("node:fs")
const path = require("node:path")

const STRING = /"((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)'|`((?:[^`\\]|\\.)*)`/g
const CLASSY = /^[!-]?[A-Za-z0-9@[(*&][^\s"'`{}\\]*$/

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) walk(p, out)
    else if (/\.(tsx?|jsx?|mdx?)$/.test(e.name)) out.push(p)
  }
  return out
}

/** Tailwind's inline parser stops at an unbalanced ( or [, so skip prose fragments like "(sim". */
function balanced(tok) {
  let round = 0
  let square = 0
  for (const ch of tok) {
    if (ch === "(") round++
    else if (ch === ")" && --round < 0) return false
    else if (ch === "[") square++
    else if (ch === "]" && --square < 0) return false
  }
  return round === 0 && square === 0
}

function candidates(srcDir) {
  const set = new Set()
  for (const file of walk(srcDir)) {
    const text = fs.readFileSync(file, "utf8")
    for (const m of text.matchAll(STRING)) {
      const s = (m[1] ?? m[2] ?? m[3] ?? "").replace(/\$\{[^}]*\}/g, " ")
      for (const tok of s.split(/\s+/)) if (tok.length > 1 && tok.length < 160 && CLASSY.test(tok) && balanced(tok)) set.add(tok)
    }
  }
  return [...set].sort()
}

const plugin = (opts = {}) => {
  const srcDir = path.resolve(opts.src ?? "src")
  return {
    postcssPlugin: "tailwind-wasm-sources",
    Once(root, { result, AtRule }) {
      const file = root.source?.input.file ?? ""
      if (!file.endsWith("globals.css")) return
      const list = candidates(srcDir).map((c) => c.replace(/"/g, '\\"')).join(" ")
      root.prepend(new AtRule({ name: "source", params: `inline("${list}")` }))
      // Next's PostCSS loader honours per-file dependencies (not dir-dependency),
      // so every scanned file is registered and edits recompile the CSS.
      for (const dep of walk(srcDir)) result.messages.push({ type: "dependency", plugin: "tailwind-wasm-sources", file: dep, parent: file })
      result.messages.push({ type: "dir-dependency", plugin: "tailwind-wasm-sources", dir: srcDir, glob: "**/*", parent: file })
    },
  }
}
plugin.postcss = true
module.exports = plugin
module.exports.candidates = candidates
