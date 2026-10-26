// Number, time and money formatting used everywhere in the UI.
// Amounts are in the dataset's (unnamed) currency, shown with "$".

export function money(v: number | null | undefined, opts: { sign?: boolean } = {}): string {
  if (v == null || Number.isNaN(v)) return "–"
  const a = Math.abs(v)
  const s = v < 0 ? "−" : opts.sign && v > 0 ? "+" : ""
  if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(2)}B`
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(a >= 1e8 ? 0 : 1)}M`
  if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(a >= 1e5 ? 0 : 1)}k`
  return `${s}$${a.toFixed(0)}`
}

export function pct(v: number | null | undefined, digits = 1): string {
  if (v == null || Number.isNaN(v)) return "–"
  return `${(v * 100).toFixed(digits)}%`
}

export function int(v: number | null | undefined): string {
  if (v == null) return "–"
  return Math.round(v).toLocaleString("en-US")
}

/** 9,876 / 14.4k / 1.52M - for counts that must fit a small card */
export function compact(v: number | null | undefined): string {
  if (v == null) return "–"
  const a = Math.abs(v)
  if (a < 10000) return Math.round(v).toLocaleString("en-US")
  if (a < 1e6) return `${(v / 1e3).toFixed(a < 1e5 ? 1 : 0)}k`
  return `${(v / 1e6).toFixed(2)}M`
}

export function duration(minutes: number | null | undefined): string {
  if (!minutes) return "0m"
  const m = Math.round(minutes)
  if (m < 60) return `${m}m`
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`
}

/** "2026-01-05T14:35:00" -> "14:35" (sim times are UTC wall-clock strings; never shift them) */
export function hhmm(iso: string | null | undefined): string {
  return iso ? iso.slice(11, 16) : "–"
}

const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

export function dayLabel(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number)
  const wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay()
  return `${WD[wd]} ${d} ${MON[m - 1]}`
}

export function minutesBetween(a: string | null, b: string | null): number {
  if (!a || !b) return 0
  return (Date.parse(b + "Z") - Date.parse(a + "Z")) / 60000
}
